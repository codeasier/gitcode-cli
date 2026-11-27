import asyncio
import base64
import hashlib
import html
import json
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from gitcode_mcp import cli_oauth_client_api as api
from gitcode_mcp.cli_oauth_browser import ENTRY
from gitcode_mcp.cli_oauth_consent import CALLBACK, CONSENT, FINISHED
from gitcode_mcp.cli_oauth_flow import Subject
from gitcode_mcp.oauth_store import OAuthStore
from gitcode_mcp.oauth_upstream import TOKEN_URL

ORIGIN = "https://broker.example"
TOKEN = "synthetic.test_token"
CODE = "fixtureCode"


@pytest.fixture
def factory(tmp_path):
    apps, calls = [], []
    key = Fernet.generate_key().decode()

    async def exchange(req):
        assert req.method == "POST" and str(req.url.copy_with(query=None)) == TOKEN_URL
        assert req.url.params.get("code") == CODE
        calls.append("exchange")
        return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 180})

    async def verify(token):
        assert token == TOKEN
        calls.append("identity")
        return Subject("123456", "verified-user")

    def make(**kwargs):
        store = OAuthStore(tmp_path / "db", key)
        options = dict(
            broker_origin=ORIGIN,
            client_id="fixture",
            client_secret="test-secret",
            verify_identity=verify,
            transport=httpx.MockTransport(exchange),
        )
        app = api.CLIOAuthBroker(store, **(options | kwargs))
        apps.append((app, store))
        return app, store

    yield make, calls
    for app, store in apps:
        asyncio.run(app.aclose())
        store.close()


def client(app):
    return httpx.AsyncClient(base_url=ORIGIN, transport=httpx.ASGITransport(app=app))


async def start(cli):
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()[:-1]
    r = await cli.post(api.START, json={"challenge": challenge})
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert set(d) == {"selector", "pairing", "browser_url"}
    assert d["browser_url"] == ORIGIN + ENTRY and d["pairing"].startswith(d["selector"] + ".")
    assert verifier not in r.text and not r.headers.get("location") and not r.cookies
    return d["pairing"], {"selector": d["selector"], "verifier": verifier}


async def consent(b, pairing, *, provider_denial=False):
    r = await b.post(ENTRY, headers={"Origin": ORIGIN}, data={"pair": pairing})
    loc = html.unescape(re.search(r'href="([^"]+)"', r.text)[1])
    assert pairing not in loc and urlsplit(loc).hostname == "gitcode.com"
    state = parse_qs(urlsplit(loc).query)["state"][0]
    params = {"error": "access_denied"} if provider_denial else {"code": CODE}
    cb = await b.get(CALLBACK, params={"state": state, **params})
    assert cb.status_code == 303 and cb.headers["location"] == (
        FINISHED if provider_denial else CONSENT
    )
    if provider_denial:
        return None
    page = await b.get(CONSENT)
    assert "verified-user" in page.text and TOKEN not in page.text
    return re.search(r'name="csrf" value="([^"]+)"', page.text)[1]


@pytest.mark.parametrize("decision", ["allow", "deny", "provider-denied"])
def test_protocol_across_restart_and_concurrent_redemption(factory, decision, caplog, tmp_path):
    make, calls = factory
    app, store = make()

    async def exercise():
        async with client(app) as cli, client(app) as browser:
            pair, proof = await start(cli)
            pending = await cli.post(api.REDEEM, json=proof)
            assert pending.status_code == 202 and pending.json() == {
                "status": "pending",
                "retry_after": 5,
            }
            assert (await cli.post(api.REDEEM, json=proof | {"verifier": "Z" * 43})).json() == {
                "status": "unavailable"
            }
            csrf = await consent(browser, pair, provider_denial=decision == "provider-denied")
            if csrf is not None:
                assert (await cli.post(api.REDEEM, json=proof)).status_code == 202
                done = await browser.post(
                    CONSENT, headers={"Origin": ORIGIN}, data={"csrf": csrf, "decision": decision}
                )
                assert done.status_code == 303 and done.headers["location"] == FINISHED
            assert calls == ([] if decision == "provider-denied" else ["exchange", "identity"])
        # Reopen the dedicated durable store. Separate processes/connections may race.
        store.close()
        left, _ = make()
        right, _ = make()
        other, _ = make(client_id="other")
        async with client(other) as wrong:
            assert (await wrong.post(api.REDEEM, json=proof)).status_code == 400
        private = [proof["verifier"], proof["selector"], pair.partition(".")[2], TOKEN]
        for f in tmp_path.rglob("*"):
            if f.is_file():
                assert all(s.encode() not in f.read_bytes() for s in private)
        async with client(left) as a, client(right) as b:
            replies = await asyncio.gather(
                a.post(api.REDEEM, json=proof), b.post(api.REDEEM, json=proof)
            )
            assert sorted(r.status_code for r in replies) == (
                [200, 400] if decision == "allow" else [400, 400]
            )
            for r in replies:
                assert (
                    not r.cookies
                    and "location" not in r.headers
                    and r.headers["cache-control"] == "no-store"
                )
                if r.status_code == 200:
                    data = r.json()
                    assert set(data) == {"status", "access_token", "expires_at", "subject", "login"}
                    assert (data["access_token"], data["subject"], data["login"]) == (
                        TOKEN,
                        "123456",
                        "verified-user",
                    )
                    assert time.time() < data["expires_at"] <= time.time() + 181
                else:
                    assert r.json() == {"status": "unavailable"}
            assert (await a.post(api.REDEEM, json=proof)).status_code == 400
        assert all(s not in caplog.text for s in private)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "case",
    [
        "wrong-method",
        "http",
        "wrong-host",
        "raw-alias",
        "query",
        "duplicate-host",
        "cookie",
        "origin",
        "referer",
        "authorization",
        "compressed",
        "chunked",
        "long",
        "duplicate-length",
        "short",
        "body-too-long",
        "non-json",
        "extra",
        "duplicate",
        "bad-ascii",
        "wrong-proof",
        "no-length",
        "deep",
        "huge-headers",
        "mounted",
    ],
)
def test_invalid_requests_do_not_enter_store(factory, case, monkeypatch):
    app, _ = factory[0]()
    monkeypatch.setattr(
        app.flow, "create", lambda *_a, **_kw: pytest.fail("unexpected store operation")
    )
    body = json.dumps({"challenge": "A" * 43}).encode()
    if case == "extra":
        body = body[:-1] + b',"unexpected":"x"}'
    if case == "duplicate":
        body = body[:-1] + b',"challenge":"A"}'
    if case == "bad-ascii":
        body = b'{"challenge":"\xff"}'
    if case == "wrong-proof":
        body = b'{"challenge":"bad"}'
    if case == "deep":
        body = b"[" * 100 + b"]" * 100
    hs = [
        (b"host", b"broker.example"),
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if case == "wrong-host":
        hs[0] = (b"host", b"not-broker.example")
    if case == "non-json":
        hs[1] = (b"content-type", b"text/plain")
    if case == "no-length":
        hs.pop()
    if case == "short":
        hs[2] = (b"content-length", b"250")
    if case == "long":
        hs[2] = (b"content-length", b"999")
    if case == "body-too-long":
        hs[2] = (b"content-length", b"2")
    if case == "duplicate-host":
        hs.append(hs[0])
    if case == "duplicate-length":
        hs.append(hs[2])
    if case == "huge-headers":
        hs.append((b"x", b"x" * 16384))
    if case in {"cookie", "origin", "referer", "authorization"}:
        hs.append((case.encode(), b"x"))
    if case == "compressed":
        hs.append((b"content-encoding", b"gzip"))
    if case == "chunked":
        hs.append((b"transfer-encoding", b"chunked"))
    scope = dict(
        type="http",
        method="GET" if case == "wrong-method" else "POST",
        scheme="http" if case == "http" else "https",
        path=api.START,
        raw_path=b"/cli/v1/%73tart" if case == "raw-alias" else api.START.encode(),
        query_string=b"x=1" if case == "query" else b"",
        root_path="/nested" if case == "mounted" else "",
        headers=hs,
    )
    out = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        out.append(msg)

    asyncio.run(app(scope, receive, send))
    assert out[0]["status"] == 400 and json.loads(out[1]["body"]) == {"status": "unavailable"}


def test_one_budget_covers_slow_body_and_sqlite_without_late_create(factory, monkeypatch):
    app, store = factory[0]()
    monkeypatch.setattr(api, "_BUDGET", 0.35)
    monkeypatch.setattr(api, "_REPLY_RESERVE", 0.05)
    peer = sqlite3.connect(store.path, isolation_level=None)
    peer.execute("BEGIN IMMEDIATE")
    body = json.dumps({"challenge": "A" * 43}).encode()
    scope = dict(
        type="http",
        method="POST",
        scheme="https",
        path=api.START,
        raw_path=api.START.encode(),
        query_string=b"",
        headers=[
            (b"host", b"broker.example"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    )

    async def run():
        out = []

        async def receive():
            await asyncio.sleep(0.14)
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(msg):
            out.append(msg)

        now = time.monotonic()
        await app(scope, receive, send)
        elapsed = time.monotonic() - now
        assert 0.24 <= elapsed < 0.48 and out[0]["status"] == 503

    try:
        asyncio.run(run())
    finally:
        peer.rollback()
        peer.close()
    with sqlite3.connect(store.path) as db:
        assert db.execute("select count(*) from oauth_records").fetchone() == (0,)


def test_consumed_receipt_is_not_replayed_after_transport_disconnect(factory):
    app, _ = factory[0]()

    async def run():
        async with client(app) as cli, client(app) as browser:
            pair, proof = await start(cli)
            csrf = await consent(browser, pair)
            assert (
                await browser.post(
                    CONSENT, headers={"Origin": ORIGIN}, data={"csrf": csrf, "decision": "allow"}
                )
            ).status_code == 303
            req = cli.build_request("POST", api.REDEEM, json=proof)
            scope = dict(
                type="http",
                method="POST",
                scheme="https",
                path=api.REDEEM,
                raw_path=api.REDEEM.encode(),
                query_string=b"",
                headers=[(k.lower(), v) for k, v in req.headers.raw],
            )

            async def receive():
                return {"type": "http.request", "body": req.content, "more_body": False}

            async def send(msg):
                if msg["type"] == "http.response.start":
                    assert msg["status"] == 200
                else:
                    raise BrokenPipeError("test disconnect")

            with pytest.raises(BrokenPipeError):
                await app(scope, receive, send)
            assert (await cli.post(api.REDEEM, json=proof)).status_code == 400

    asyncio.run(run())


def test_independent_fixed_admission_buckets(factory):
    app, _ = factory[0]()
    assert all(app._admit_api(api.START) for _ in range(20))
    assert not app._admit_api(api.START)
    assert all(app._admit_api(api.REDEEM) for _ in range(120))
    assert not app._admit_api(api.REDEEM)
    assert app._admit()


@pytest.mark.parametrize("when", ["while-pending", "after-approval"])
def test_expiration_survives_reopen_and_never_returns_a_receipt(factory, monkeypatch, when):
    from gitcode_mcp import cli_oauth_flow

    make, _ = factory
    app, store = make()

    async def run():
        async with client(app) as c, client(app) as browser:
            pair, proof = await start(c)
            if when == "after-approval":
                csrf = await consent(browser, pair)
                assert (
                    await browser.post(
                        CONSENT,
                        headers={"Origin": ORIGIN},
                        data={"csrf": csrf, "decision": "allow"},
                    )
                ).status_code == 303
            store.close()
            app2, _ = make()
            future = time.time() + 310
            monkeypatch.setattr(cli_oauth_flow.time, "time", lambda: future)
            async with client(app2) as c2:
                fail = await c2.post(api.REDEEM, json=proof)
                assert fail.status_code == 400 and fail.json() == {"status": "unavailable"}

    asyncio.run(run())


@pytest.mark.parametrize("after_commit", [False, True])
def test_worker_does_not_publish_a_late_receipt(factory, monkeypatch, after_commit):
    import threading

    from gitcode_mcp.oauth_store import OAuthTransaction

    app, store = factory[0]()

    async def run():
        loop = asyncio.get_running_loop()
        reached = asyncio.Event()
        release = threading.Event()
        async with client(app) as c, client(app) as browser:
            pair, proof = await start(c)
            csrf = await consent(browser, pair)
            assert (
                await browser.post(
                    CONSENT, headers={"Origin": ORIGIN}, data={"csrf": csrf, "decision": "allow"}
                )
            ).status_code == 303
            # Deliberately pause either after SQL mutation but before COMMIT, or after COMMIT.
            original = app.flow.redeem if after_commit else OAuthTransaction.delete

            def delayed(*a, **kw):
                res = original(*a, **kw)
                loop.call_soon_threadsafe(reached.set)
                assert release.wait(3)
                return res

            monkeypatch.setattr(
                app.flow if after_commit else OAuthTransaction,
                "redeem" if after_commit else "delete",
                delayed,
            )
            monkeypatch.setattr(api, "_BUDGET", 0.22)
            monkeypatch.setattr(api, "_REPLY_RESERVE", 0.04)
            try:
                task = asyncio.create_task(c.post(api.REDEEM, json=proof))
                await asyncio.wait_for(reached.wait(), 2)
                reply = await asyncio.wait_for(task, 2)
                assert reply.status_code == 503 and reply.json() == {"status": "unavailable"}
            finally:
                release.set()
            row = await asyncio.to_thread(store.get, "flow", "cli.oauth.v1:" + proof["selector"])
            if after_commit:
                assert row is None
            else:
                assert row["phase"] == "ready"

    asyncio.run(run())
