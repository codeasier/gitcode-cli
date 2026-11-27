"""The native client contract. All broker, account and proof fixtures are disposable."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path

import httpx
import pytest

from gitcode_cli import oauth_broker_client as client
from gitcode_cli.errors import AuthError

ORIGIN = "https://broker.invalid"
ENTRY = ORIGIN + "/cli/v1/browser"


def start():
    selector, proof = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    return {"selector": selector, "pairing": selector + "." + proof, "browser_url": ENTRY}


def authorized():
    return {
        "status": "authorized",
        "access_token": secrets.token_urlsafe(32),
        "subject": "199",
        "login": "fixture-login",
        "expires_at": int(time.time()) + 180,
    }


class Wire(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        for i in range(0, len(self.data), 9):
            yield self.data[i : i + 9]


def response(status, obj, **kwargs):
    raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    headers = {"content-type": "application/json", "cache-control": "no-store", **kwargs}
    return httpx.Response(status, headers=headers, stream=Wire(raw))


def scenario(replies):
    queue, calls, shown = list(replies), [], []

    def dispatch(req):
        calls.append(req)
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        logging.getLogger("httpcore.http11").debug("fixture-private-header")
        return result

    async def present(url, pair):
        shown.append((url, pair))

    return httpx.MockTransport(dispatch), present, calls, shown


def run(data):
    tr, show, _, _ = data
    return asyncio.run(client.acquire_receipt(ORIGIN, show, _transport=tr))


def test_roundtrip_only_pending_can_poll(monkeypatch, caplog, tmp_config_dir):
    config = Path(tmp_config_dir)
    before = {p: p.read_bytes() for p in config.rglob("*") if p.is_file()}
    first, final = start(), authorized()
    data = scenario(
        [response(201, first), response(202, {"status": "pending", "retry_after": 5}), response(200, final)]
    )
    delays = []

    async def sleep(s):
        delays.append(s)

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    monkeypatch.setenv("GC_TOKEN", "unrelated-local-override")
    monkeypatch.setenv("HTTPS_PROXY", "https://unused.invalid")
    with caplog.at_level(logging.DEBUG):
        receipt = run(data)
        logging.getLogger("httpcore.http11").debug("outside-transaction")
    _, _, calls, shown = data
    assert delays == [5] and len(calls) == 3
    assert shown == [(ENTRY, first["pairing"])]
    assert [str(r.url) for r in calls] == [
        ORIGIN + "/cli/v1/start",
        ORIGIN + "/cli/v1/redeem",
        ORIGIN + "/cli/v1/redeem",
    ]
    for req in calls:
        assert req.method == "POST" and req.headers["content-type"] == "application/json"
        assert int(req.headers["content-length"]) == len(req.content) <= 256
        assert not set(req.headers) & {
            "authorization",
            "proxy-authorization",
            "cookie",
            "origin",
            "referer",
            "transfer-encoding",
            "content-encoding",
        }
        assert "unrelated-local-override" not in repr(req.headers)
    redeem = json.loads(calls[1].content)
    assert calls[1].content == calls[2].content
    assert set(redeem) == {"selector", "verifier"} and redeem["selector"] == first["selector"]
    verifier = redeem["verifier"]
    assert len(base64.urlsafe_b64decode(verifier + "=")) == 32 and verifier not in repr(shown)
    assert json.loads(calls[0].content) == {
        "challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    }
    assert (
        receipt.access_token == final["access_token"] and receipt.subject == "199" and receipt.login == "fixture-login"
    )
    for private in (first["pairing"], first["selector"], verifier, final["access_token"], "fixture-private-header"):
        assert private not in caplog.text and private not in repr(receipt)
    assert "outside-transaction" in caplog.text
    assert {p: p.read_bytes() for p in config.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "https://user@host",
        "https://a.invalid/",
        "https://a.invalid/p",
        "https://a.invalid?",
        "https://a.invalid#",
        "https://a.invalid?q=x",
        "https://a.invalid:443",
        "//a.invalid",
        "https://a.invalid:000",
        "https://a.invalid:65536",
        "https://foo%2einvalid",
        "https://host\\evil",
        "https://127.1",
        "https://0177.0.0.1",
        "https://xn--a.0x1",
        "https://a.invalid\n",
        "https://.foo",
    ],
)
def test_unsafe_origin_has_no_http_or_present(origin):
    tr, show, calls, shown = scenario([])
    with pytest.raises(AuthError, match="canonical HTTPS"):
        asyncio.run(client.acquire_receipt(origin, show, _transport=tr))
    assert calls == [] and shown == []


@pytest.mark.parametrize(
    "override",
    [
        {"browser_url": "https://gitcode.com/cli/v1/browser"},
        {"browser_url": ENTRY + "?pair=private"},
        {"browser_url": "/cli/v1/browser"},
        {"browser_url": ENTRY + "#"},
        {"browser_url": "https://broker.invalid@untrusted.invalid/cli/v1/browser"},
        {"selector": "other"},
        {"pairing": "bad"},
        {"pairing": "A" * 43 + "." + "A" * 43},
        {"issuer": ORIGIN},
    ],
)
def test_rejects_corrupt_start_without_opening(override):
    data = scenario([response(201, {**start(), **override})])
    with pytest.raises(AuthError, match="Invalid OAuth"):
        run(data)
    assert len(data[2]) == 1 and not data[3]


@pytest.mark.parametrize("status", [201, 204, 302, 303, 307, 308, 400, 401, 403, 429, 500, 503])
def test_error_or_redirect_never_replays_or_follows(status):
    data = scenario(
        [response(201, start()), response(status, {"detail": "private-marker"}, location="https://other.invalid")]
    )
    with pytest.raises(AuthError) as err:
        run(data)
    assert "private-marker" not in str(err.value)
    assert len(data[2]) == 2 and all(req.url.host == "broker.invalid" for req in data[2])


@pytest.mark.parametrize(
    "pending",
    [
        {"status": "pending", "retry_after": True},
        {"status": "pending", "retry_after": 5.0},
        {"status": "pending", "retry_after": "5"},
        {"status": "pending", "retry_after": 0},
        {"status": "pending", "retry_after": 5, "url": "https://other.invalid"},
        {},
    ],
)
def test_bad_pending_never_polls(pending):
    data = scenario([response(201, start()), response(202, pending)])
    with pytest.raises(AuthError):
        run(data)
    assert len(data[2]) == 2


@pytest.mark.parametrize(
    "patch",
    [
        {"expires_at": True},
        {"expires_at": 0},
        {"expires_at": float("inf")},
        {"expires_at": float("nan")},
        {"subject": 123},
        {"subject": "bad subject"},
        {"login": "../bad"},
        {"access_token": "bad token"},
        {"status": "pending"},
        {"next": "https://other.invalid"},
    ],
)
def test_rejects_bad_receipt(patch):
    data = scenario([response(201, start()), response(200, {**authorized(), **patch})])
    with pytest.raises(AuthError):
        run(data)
    assert len(data[2]) == 2


@pytest.mark.parametrize(
    "body,headers",
    [
        (b"{}", {"content-encoding": "gzip"}),
        (b"{}", {"set-cookie": "g=x"}),
        (b"{}", {"location": ENTRY}),
        (b"{}", {"cache-control": "public"}),
        (b"{}", {"content-type": "text/html"}),
        (b"{}", {"content-length": "9"}),
        (b"x" * 16385, {}),
        (b"{}", {"content-length": "99999"}),
        (b"\xff", {}),
        (b'{"a":1,"a":2}', {}),
        (b"[1]", {}),
        (b"[" * 2000 + b"]" * 2000, {}),
        (b"{}", {"x-junk": "A" * 17000}),
    ],
)
def test_bad_transport_or_shape(body, headers):
    data = scenario([response(201, body, **headers)])
    with pytest.raises(AuthError, match="Invalid OAuth"):
        run(data)
    assert len(data[2]) == 1 and not data[3]


def test_uncertain_redeem_leaks_nothing_and_is_not_replayed():
    data = scenario([response(201, start()), httpx.ReadError("private-receipt-marker")])
    with pytest.raises(AuthError, match="outcome may be unknown") as err:
        run(data)
    assert "private-receipt-marker" not in str(err.value) and not err.value.__cause__
    assert len(data[2]) == 2


def test_pending_cancel_or_deadline_no_automatic_next_request(monkeypatch):
    async def blocked(url, pair):
        await asyncio.Event().wait()

    async def cancel():
        tr, _, calls, _ = scenario([response(201, start())])
        ready = asyncio.Event()

        async def present(url, pair):
            ready.set()
            await blocked(url, pair)

        task = asyncio.create_task(client.acquire_receipt(ORIGIN, present, _transport=tr))
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) == 1

    asyncio.run(cancel())
    tr, _, calls, _ = scenario([response(201, start())])
    monkeypatch.setattr(client, "_TOTAL_TIMEOUT", 0.02)
    with pytest.raises(AuthError, match="outcome may be unknown"):
        asyncio.run(client.acquire_receipt(ORIGIN, blocked, _transport=tr))
    assert len(calls) == 1


def test_independent_transactions_have_independent_challenges():
    a, b = start(), start()
    first, second = (
        scenario([response(201, a), response(200, authorized())]),
        scenario([response(201, b), response(200, authorized())]),
    )
    run(first)
    run(second)
    assert first[2][0].content != second[2][0].content and first[2][1].content != second[2][1].content
