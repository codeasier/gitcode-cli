import asyncio
import base64
import hashlib
import html
import logging
import re
import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from gitcode_mcp import cli_oauth_browser as mod
from gitcode_mcp.cli_oauth_browser import COOKIE, ENTRY, CLIBrowserEntry
from gitcode_mcp.cli_oauth_flow import FlowRejected
from gitcode_mcp.oauth_store import OAuthStore

ORIGIN = "https://broker.example"
FORM = {"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def setup(tmp_path):
    async def identity(token):
        raise AssertionError("browser entry must not look up identity")

    store = OAuthStore(tmp_path / "cli.sqlite", Fernet.generate_key().decode())
    app = CLIBrowserEntry(
        store, broker_origin=ORIGIN, client_id="app.test", verify_identity=identity
    )
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()[:-1]
    start = app.flow.create(challenge)
    yield app, start, verifier
    store.close()


def pair(start):
    return f"pair={start.selector}.{start.browser_start}"


def request(app, method, path=ENTRY, *, headers=None, body=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as c:
            return await c.request(method, path, headers=headers, content=body)

    return asyncio.run(run())


def cookie(response):
    values = SimpleCookie()
    values.load(response.headers["set-cookie"])
    return values[COOKIE]


def target(response):
    return urlsplit(html.unescape(re.search(r'href="([^"]+)"', response.text).group(1)))


def test_pair_once_on_pinned_origin_with_separate_browser_secret(setup, caplog):
    caplog.set_level(logging.DEBUG)
    app, start, private = setup
    page = request(app, "GET")
    assert page.status_code == 200
    assert 'method="post"' in page.text and f'action="{ENTRY}"' in page.text
    assert "set-cookie" not in page.headers
    assert all(secret not in page.text for secret in (private, start.selector, start.browser_start))
    yes = request(app, "POST", headers=FORM, body=pair(start))
    assert yes.status_code == 200 and "location" not in yes.headers
    assert yes.headers["referrer-policy"] == "no-referrer"
    assert yes.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in yes.headers["content-security-policy"]
    assert 'http-equiv="refresh"' in yes.text
    auth = target(yes)
    assert (auth.scheme, auth.netloc, auth.path, auth.fragment) == (
        "https",
        "gitcode.com",
        "/oauth/authorize",
        "",
    )
    params = parse_qs(auth.query)
    state = params.pop("state")[0]
    assert params == {
        "client_id": ["app.test"],
        "response_type": ["code"],
        "redirect_uri": [ORIGIN + "/cli/v1/callback"],
        "prompt": ["consent"],
    }
    session = cookie(yes)
    selector, binding = session.value.split(".")
    assert selector == start.selector and binding not in (start.browser_start, state, private)
    assert session["secure"] and session["httponly"] and session["path"] == "/"
    assert not session["domain"] and session["samesite"] == "lax" and session["max-age"] == "300"
    assert all(s not in yes.text for s in (private, start.selector, start.browser_start, binding))
    duplicate = request(app, "POST", headers=FORM, body=pair(start))
    assert duplicate.status_code == 400 and "set-cookie" not in duplicate.headers
    with pytest.raises(FlowRejected):
        app.flow.claim_callback(start.selector, start.browser_start, state)
    claim = app.flow.claim_callback(selector, binding, state)
    assert claim and all(
        v not in caplog.text
        for v in (private, selector, binding, start.browser_start, state, claim.proof)
    )


@pytest.mark.parametrize(
    ("method", "path", "headers", "body"),
    [
        ("POST", ENTRY, {}, "pair"),
        ("POST", ENTRY, {"Origin": "null"}, "pair"),
        ("POST", ENTRY, {"Origin": "https://else.example"}, "pair"),
        ("POST", ENTRY, {"Host": "else.example"}, "pair"),
        ("POST", ENTRY, {"Content-Type": "text/plain"}, "pair"),
        ("POST", ENTRY, {"Content-Encoding": "gzip"}, "pair"),
        ("POST", ENTRY, {"Cookie": COOKIE + "=older"}, "pair"),
        ("POST", ENTRY, {"Content-Length": "999"}, "pair"),
        ("POST", ENTRY, {}, "short"),
        ("POST", ENTRY, {}, "long"),
        ("POST", ENTRY + "?where=elsewhere", {}, "pair"),
        ("PUT", ENTRY, {}, "pair"),
        ("GET", "/mcp", {}, None),
        ("GET", "/cli/v1/callback", {}, None),
        ("GET", "http://broker.example" + ENTRY, {}, None),
    ],
)
def test_reject_before_consumption(setup, method, path, headers, body):
    app, start, _ = setup
    fixed = FORM | headers
    if body == "pair":
        content = pair(start)
    elif body == "short":
        content = "pair=short"
    elif body == "long":
        content = pair(start) + "&selector=other"
    else:
        content = None
    # First case specifically exercises the absent Origin header.
    if method == "POST" and path == ENTRY and headers == {} and body == "pair":
        fixed.pop("Origin")
    failed = request(app, method, path, headers=fixed, body=content)
    assert (failed.status_code, failed.text) == (400, "CLI authorization transaction unavailable.")
    assert "set-cookie" not in failed.headers and "location" not in failed.headers
    assert request(app, "POST", headers=FORM, body=pair(start)).status_code == 200


def test_duplicate_origin_and_host_rejected(setup):
    app, start, _ = setup
    for key, value in [("origin", ORIGIN), ("host", "broker.example")]:
        headers = list(FORM.items())
        if key == "host":
            headers.append(("host", "broker.example"))
        headers.append((key, value))
        res = request(app, "POST", headers=headers, body=pair(start))
        assert res.status_code == 400
    assert request(app, "POST", headers=FORM, body=pair(start)).status_code == 200


def test_bounded_global_admission_no_selector_allocation(setup):
    app, start, _ = setup
    wrong = "pair=" + "a" * 43 + "." + "b" * 43
    for _ in range(60):
        assert request(app, "POST", headers=FORM, body=wrong).status_code == 400
    limited = request(app, "POST", headers=FORM, body=pair(start))
    assert limited.status_code == 429
    assert limited.text == "CLI authorization transaction unavailable."
    assert "set-cookie" not in limited.headers


def test_bounded_chunked_body_without_length(setup):
    app, start, _ = setup

    async def run():
        async def chunks():
            yield pair(start).encode()
            yield b"x"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as c:
            return await c.post(ENTRY, headers=FORM, content=chunks())

    assert asyncio.run(run()).status_code == 400
    assert request(app, "POST", headers=FORM, body=pair(start)).status_code == 200


def test_irrelevant_cookie_is_not_a_binding(setup):
    app, start, _ = setup
    ready = request(
        app, "POST", headers=FORM | {"Cookie": "unrelated=" + COOKIE + "=value"}, body=pair(start)
    )
    assert ready.status_code == 200


def test_header_and_total_body_time_bounds_before_begin(setup, monkeypatch):
    app, start, _ = setup
    res = request(app, "POST", headers=FORM | {"X-Unknown": "z" * 16384}, body=pair(start))
    assert res.status_code == 400
    monkeypatch.setattr(mod, "_READ_DEADLINE", 0.01)

    async def run():
        async def stalled():
            yield b"pair="
            await asyncio.sleep(1)
            yield pair(start).encode()[5:]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as c:
            return await c.post(ENTRY, headers=FORM, content=stalled())

    assert asyncio.run(run()).status_code == 400
    monkeypatch.setattr(mod, "_READ_DEADLINE", 5.0)
    assert request(app, "POST", headers=FORM, body=pair(start)).status_code == 200
