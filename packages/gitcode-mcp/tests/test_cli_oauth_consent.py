import asyncio
import base64
import hashlib
import html
import re
import secrets
import sqlite3
import threading
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from gitcode_mcp.cli_oauth_browser import COOKIE, ENTRY
from gitcode_mcp.cli_oauth_consent import CALLBACK, CONSENT, FINISHED, CLIBrowserConsent
from gitcode_mcp.cli_oauth_flow import FlowRejected, Subject
from gitcode_mcp.oauth_store import OAuthStore, OAuthTransaction
from gitcode_mcp.oauth_upstream import TOKEN_URL

ORIGIN = "https://broker.example"
FORM = {"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def broker(tmp_path):
    receipt = []
    token = "fixture-server-only.access"
    secret = "fixture-client-secret"
    code = "fixture.authorization-code"

    async def upstream(req):
        receipt.append("token")
        assert req.method == "POST"
        url = req.url
        assert str(url.copy_with(query=None)) == TOKEN_URL
        assert dict(url.params) == {
            "code": code,
            "client_id": "app",
            "grant_type": "authorization_code",
        }
        assert secret not in str(url) and secret.encode() in await req.aread()
        assert "authorization" not in req.headers and "cookie" not in req.headers
        return httpx.Response(200, json={"access_token": token, "expires_in": 120})

    async def verify(value):
        assert value == token
        receipt.append("identity")
        return Subject("2468", "name<test>")

    store = OAuthStore(tmp_path / "store", Fernet.generate_key().decode())
    app = CLIBrowserConsent(
        store,
        broker_origin=ORIGIN,
        client_id="app",
        client_secret=secret,
        verify_identity=verify,
        transport=httpx.MockTransport(upstream),
    )
    try:
        yield app, receipt, token, code
    finally:
        asyncio.run(app.aclose())
        store.close()


def client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN, follow_redirects=False
    )


async def pair(app, cli):
    private = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(private.encode()).digest()).decode()[:-1]
    start = app.flow.create(challenge)
    result = await cli.post(
        ENTRY, data={"pair": start.selector + "." + start.browser_start}, headers={"Origin": ORIGIN}
    )
    assert result.status_code == 200
    link = html.unescape(re.search(r'href="([^"]+)"', result.text)[1])
    state = parse_qs(urlsplit(link).query)["state"][0]
    return start, private, state


def csrf(page):
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert "name&lt;test&gt;" in page.text and "<test>" not in page.text and "2468" in page.text
    return re.search(r'name="csrf" value="([^"]+)"', page.text)[1]


@pytest.mark.parametrize("decision", ["allow", "deny"])
def test_explicit_decision_only_after_clean_callback(broker, decision):
    app, receipt, token, code = broker

    async def run():
        async with client(app) as cli, client(app) as stranger:
            start, private, state = await pair(app, cli)
            raw_cookie = cli.cookies.get(COOKIE)
            chain = await cli.get(CALLBACK, params={"state": state, "code": code})
            assert chain.status_code == 303 and chain.headers["location"] == CONSENT
            assert receipt == ["token", "identity"]
            assert chain.headers["referrer-policy"] == "no-referrer"
            assert (await stranger.get(CONSENT)).status_code == 400
            a = await cli.get(CONSENT)
            first = csrf(a)
            b = await cli.get(CONSENT)
            fresh = csrf(b)
            assert fresh != first
            for value in [
                start.selector,
                start.browser_start,
                private,
                raw_cookie,
                token,
                state,
                code,
            ]:
                assert value not in chain.text + chain.headers["location"] + b.text
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)
            bad = await cli.post(CONSENT, headers=FORM, data={"decision": decision, "csrf": first})
            assert bad.status_code == 400
            done = await cli.post(CONSENT, headers=FORM, data={"csrf": fresh, "decision": decision})
            assert (done.status_code, done.headers["location"]) == (303, FINISHED)
            assert COOKIE not in cli.cookies and "max-age=0" in done.headers["set-cookie"].lower()
            assert "samesite=lax" in done.headers["set-cookie"].lower()
            assert (await cli.get(FINISHED)).text == (await stranger.get(FINISHED)).text
            if decision == "allow":
                result = app.flow.redeem(start.selector, private)
                assert result.access_token == token
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


def test_concurrent_callback_exactly_once_and_no_cookie_clear_for_loser(broker):
    app, receipt, _, code = broker

    async def run():
        async with client(app) as cli:
            _, _, state = await pair(app, cli)
            a, b = await asyncio.gather(
                *[cli.get(CALLBACK, params={"state": state, "code": code}) for _ in range(2)]
            )
            assert sorted([a.headers["location"], b.headers["location"]]) == sorted(
                [CONSENT, FINISHED]
            )
            assert all("set-cookie" not in r.headers for r in (a, b))
            assert receipt == ["token", "identity"]
            assert csrf(await cli.get(CONSENT))

    asyncio.run(run())


@pytest.mark.parametrize(
    "bad",
    [
        "wrong-cookie",
        "duplicate-cookie",
        "wrong-state",
        "bad-percent",
        "missing",
        "both",
        "huge",
        "duplicate-code",
        "extra-field",
        "denial-wrong-state",
    ],
)
def test_bad_callbacks_do_not_consume_or_exchange(broker, bad):
    app, receipt, _, code = broker

    async def run():
        async with client(app) as cli, client(app) as other:
            _, _, state = await pair(app, cli)
            cookie = cli.cookies.get(COOKIE)
            cookie_header = f"{COOKIE}={cookie}"
            raw = f"state={state}&code={code}"
            if bad == "wrong-cookie":
                cookie_header = f"{COOKIE}={cookie.split('.')[0]}." + "A" * 43
            if bad == "duplicate-cookie":
                cookie_header += "; " + cookie_header
            if bad == "wrong-state":
                raw = raw.replace(state, "B" * 43)
            if bad == "bad-percent":
                raw += "%XX"
            if bad == "missing":
                raw = f"state={state}"
            if bad == "both":
                raw += "&error=access_denied"
            if bad == "huge":
                raw += "C" * 4096
            if bad == "duplicate-code":
                raw += "&code=second"
            if bad == "extra-field":
                raw += "&redirect_uri=https://external.invalid"
            if bad == "denial-wrong-state":
                raw = "state=" + "B" * 43 + "&error=access_denied"
            denied = await other.get(CALLBACK + "?" + raw, headers={"Cookie": cookie_header})
            assert denied.status_code == 303 and denied.headers["location"] == FINISHED
            assert "set-cookie" not in denied.headers and receipt == []
            assert (await cli.get(CALLBACK, params={"code": code, "state": state})).headers[
                "location"
            ] == CONSENT

    asyncio.run(run())


def test_upstream_denial_is_neutral_and_one_use(broker):
    app, receipt, _, code = broker

    async def run():
        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            cookie = cli.cookies.get(COOKIE)
            denied = await cli.get(
                CALLBACK,
                params={
                    "state": state,
                    "error": "access_denied",
                    "error_description": "upstream text",
                },
            )
            assert (
                denied.status_code == 303
                and denied.headers["location"] == FINISHED
                and COOKIE not in cli.cookies
            )
            again = await cli.get(
                CALLBACK,
                params={"state": state, "code": code},
                headers={"Cookie": f"{COOKIE}={cookie}"},
            )
            assert (
                again.headers["location"] == FINISHED
                and not receipt
                and "upstream text" not in denied.text
            )
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


@pytest.mark.parametrize(
    "headers,body",
    [
        ({}, "csrf={}&decision=allow"),
        ({"Origin": "https://wrong.example"}, "csrf={}&decision=allow"),
        ({"Origin": ORIGIN, "Content-Type": "text/plain"}, "csrf={}&decision=allow"),
        ({"Origin": ORIGIN, "Content-Encoding": "gzip"}, "csrf={}&decision=allow"),
        ({"Origin": ORIGIN}, "csrf={}&decision=allow&decision=allow"),
        ({"Origin": ORIGIN}, "csrf={}&decision=ALLOW"),
    ],
)
def test_consent_fails_closed_without_consuming_valid_proof(broker, headers, body):
    app, receipt, token, code = broker

    async def run():
        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            await cli.get(CALLBACK, params={"code": code, "state": state})
            proof = csrf(await cli.get(CONSENT))
            bad = await cli.post(
                CONSENT,
                content=body.format(proof),
                headers={"Content-Type": FORM["Content-Type"]} | headers,
            )
            assert bad.status_code == 400 and proof not in bad.text and token not in bad.text
            assert receipt == ["token", "identity"]
            ok = await cli.post(CONSENT, headers=FORM, data={"decision": "deny", "csrf": proof})
            assert ok.status_code == 303
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


def test_callback_failure_does_not_retry_or_reflect_upstream(broker, monkeypatch):
    app, _, token, code = broker
    used = 0

    async def bad(_):
        nonlocal used
        used += 1
        raise FlowRejected()

    monkeypatch.setattr(app._upstream, "exchange_code", bad)

    async def run():
        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            cookie = cli.cookies.get(COOKIE)
            failed = await cli.get(CALLBACK, params={"code": code, "state": state})
            assert failed.status_code == 303 and failed.headers["location"] == FINISHED
            again = await cli.get(
                CALLBACK,
                params={"code": code, "state": state},
                headers={"Cookie": f"{COOKIE}={cookie}"},
            )
            assert again.headers["location"] == FINISHED and used == 1
            assert state not in again.text and token not in again.text
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


def test_two_paired_browsers_cannot_mix_callback_state_or_consent(broker):
    app, receipt, token, code = broker

    async def run():
        async with client(app) as first, client(app) as second:
            first_start, first_private, first_state = await pair(app, first)
            second_start, second_private, second_state = await pair(app, second)
            assert (
                await second.get(CALLBACK, params={"code": code, "state": first_state})
            ).headers["location"] == FINISHED
            assert receipt == []
            assert (await first.get(CALLBACK, params={"code": code, "state": first_state})).headers[
                "location"
            ] == CONSENT
            assert (
                await second.get(CALLBACK, params={"code": code, "state": second_state})
            ).headers["location"] == CONSENT
            proof1, proof2 = csrf(await first.get(CONSENT)), csrf(await second.get(CONSENT))
            assert (
                await second.post(CONSENT, data={"decision": "allow", "csrf": proof1}, headers=FORM)
            ).status_code == 400
            assert (
                await first.post(CONSENT, data={"decision": "allow", "csrf": proof1}, headers=FORM)
            ).status_code == 303
            assert (
                await second.post(CONSENT, data={"decision": "deny", "csrf": proof2}, headers=FORM)
            ).status_code == 303
            assert app.flow.redeem(first_start.selector, first_private).access_token == token
            with pytest.raises(FlowRejected):
                app.flow.redeem(second_start.selector, second_private)

    asyncio.run(run())


def test_deadline_after_claim_rejects_replay(broker, monkeypatch):
    app, _, _, code = broker
    used = []

    async def stall(_):
        used.append(True)
        await asyncio.sleep(5)

    async def run():
        async with client(app) as cli:
            _, _, state = await pair(app, cli)
            cookie = cli.cookies.get(COOKIE)
            params = {"code": code, "state": state}
            failed = await cli.get(CALLBACK, params=params)
            assert failed.status_code == 303 and failed.headers["location"] == FINISHED
            assert (
                await cli.get(CALLBACK, params=params, headers={"Cookie": f"{COOKIE}={cookie}"})
            ).headers["location"] == FINISHED
            assert used == [True]

    monkeypatch.setattr("gitcode_mcp.cli_oauth_consent._CALLBACK_DEADLINE", 0.1)
    monkeypatch.setattr(app._upstream, "exchange_code", stall)
    asyncio.run(run())


@pytest.mark.parametrize("lock_kind", ["local", "sqlite-writer", "sqlite-reader"])
@pytest.mark.parametrize("decision", ["allow", "deny"])
def test_expired_consent_cannot_commit_while_store_contended(
    broker, monkeypatch, decision, lock_kind
):
    app, _, _, code = broker
    store = app.flow._store
    original = app.flow.decide
    monkeypatch.setattr("gitcode_mcp.cli_oauth_consent._FORM_DEADLINE", 0.12)

    async def run():
        loop = asyncio.get_running_loop()
        dispatched = asyncio.Event()
        finished = asyncio.Event()

        def capture(*args, **kwargs):
            loop.call_soon_threadsafe(dispatched.set)
            try:
                return original(*args, **kwargs)
            finally:
                loop.call_soon_threadsafe(finished.set)

        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            await cli.get(CALLBACK, params={"code": code, "state": state})
            proof = csrf(await cli.get(CONSENT))
            key = "cli.oauth.v1:" + start.selector
            before = store.get("flow", key)
            default_busy = store._connection().execute("PRAGMA busy_timeout").fetchone()
            monkeypatch.setattr(app.flow, "decide", capture)
            if lock_kind == "local":
                store._lock.acquire()
                peer = None
            else:
                peer = sqlite3.connect(store.path, isolation_level=None)
                peer.execute("BEGIN IMMEDIATE" if lock_kind == "sqlite-writer" else "BEGIN")
                # Hold a writer lock at BEGIN or a reader lock that blocks commit.
                peer.execute("SELECT COUNT(*) FROM oauth_records").fetchone()
            try:
                pending = asyncio.create_task(
                    cli.post(CONSENT, headers=FORM, data={"decision": decision, "csrf": proof})
                )
                await asyncio.wait_for(dispatched.wait(), timeout=2)
                result = await asyncio.wait_for(pending, timeout=2)
            finally:
                if peer:
                    peer.rollback()
                    peer.close()
                else:
                    store._lock.release()
            await asyncio.wait_for(finished.wait(), timeout=2)
            assert store.get("flow", key) == before
            assert store._connection().execute("PRAGMA busy_timeout").fetchone() == default_busy
            assert (result.status_code, result.headers["location"]) == (303, FINISHED)
            assert "set-cookie" not in result.headers
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)
            # Unchanged phase and CSRF are still usable; no stale new or terminal state.
            good = await cli.post(CONSENT, headers=FORM, data={"decision": "deny", "csrf": proof})
            assert good.status_code == 303 and store.get("flow", key) is None

    asyncio.run(run())


@pytest.mark.parametrize("decision", ["allow", "deny"])
def test_expiry_after_sql_mutation_rolls_back_before_commit(broker, monkeypatch, decision):
    app, _, _, code = broker
    store = app.flow._store
    monkeypatch.setattr("gitcode_mcp.cli_oauth_consent._FORM_DEADLINE", 0.12)
    original_put, original_delete = OAuthTransaction.put, OAuthTransaction.delete

    async def run():
        loop = asyncio.get_running_loop()
        mutated = asyncio.Event()
        unpause = threading.Event()
        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            await cli.get(CALLBACK, params={"code": code, "state": state})
            proof = csrf(await cli.get(CONSENT))
            key = "cli.oauth.v1:" + start.selector
            before = store.get("flow", key)

            def delayed_after_mutation():
                loop.call_soon_threadsafe(mutated.set)
                assert unpause.wait(3)

            def put(self, kind, name, payload, expires_at):
                original_put(self, kind, name, payload, expires_at)
                if kind == "flow" and name == key and payload["phase"] == "ready":
                    delayed_after_mutation()

            def delete(self, kind, name):
                original_delete(self, kind, name)
                if kind == "flow" and name == key:
                    delayed_after_mutation()

            monkeypatch.setattr(
                OAuthTransaction,
                "put" if decision == "allow" else "delete",
                put if decision == "allow" else delete,
            )
            try:
                pending = asyncio.create_task(
                    cli.post(CONSENT, headers=FORM, data={"decision": decision, "csrf": proof})
                )
                await asyncio.wait_for(mutated.wait(), timeout=2)
                result = await asyncio.wait_for(pending, timeout=2)
            finally:
                unpause.set()
            # Read blocks until the canceled request's worker rolls back/releases the lock.
            assert await asyncio.to_thread(store.get, "flow", key) == before
            assert (result.status_code, result.headers["location"]) == (303, FINISHED)
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


@pytest.mark.parametrize("decision", ["allow", "deny"])
def test_delayed_acknowledgement_of_committed_choice_is_neutral(broker, monkeypatch, decision):
    app, _, token, code = broker
    store = app.flow._store
    original = app.flow.decide
    monkeypatch.setattr("gitcode_mcp.cli_oauth_consent._FORM_DEADLINE", 0.12)

    async def run():
        loop = asyncio.get_running_loop()
        committed = asyncio.Event()
        release_ack = threading.Event()

        def delayed_ack(*args, **kwargs):
            original(*args, **kwargs)
            if not committed.is_set():
                loop.call_soon_threadsafe(committed.set)
                assert release_ack.wait(3)

        async with client(app) as cli:
            start, private, state = await pair(app, cli)
            await cli.get(CALLBACK, params={"code": code, "state": state})
            proof = csrf(await cli.get(CONSENT))
            monkeypatch.setattr(app.flow, "decide", delayed_ack)
            try:
                pending = asyncio.create_task(
                    cli.post(CONSENT, headers=FORM, data={"decision": decision, "csrf": proof})
                )
                await asyncio.wait_for(committed.wait(), timeout=2)
                result = await asyncio.wait_for(pending, timeout=2)
            finally:
                release_ack.set()
            assert (result.status_code, result.headers["location"]) == (303, FINISHED)
            assert "set-cookie" not in result.headers
            assert token not in (await cli.get(FINISHED)).text
            key = "cli.oauth.v1:" + start.selector
            receipt = store.get("flow", key)
            if decision == "allow":
                assert receipt["phase"] == "ready" and not {"cookie", "csrf"} & receipt.keys()
            else:
                assert receipt is None
            repeated = await cli.post(
                CONSENT, headers=FORM, data={"decision": decision, "csrf": proof}
            )
            assert repeated.status_code == 400
            assert store.get("flow", key) == receipt
            if decision == "allow":
                assert app.flow.redeem(start.selector, private).access_token == token
            with pytest.raises(FlowRejected):
                app.flow.redeem(start.selector, private)

    asyncio.run(run())


def test_callback_verification_and_consent_sql_work_runs_off_event_loop(broker, monkeypatch):
    app, _, _, code = broker
    original = app.flow._save
    writes = {}

    def capture(tx, selector, row, phase):
        if phase in {"verifying", "consent"}:
            writes[phase] = threading.get_ident()
        return original(tx, selector, row, phase)

    monkeypatch.setattr(app.flow, "_save", capture)

    async def run():
        async with client(app) as cli:
            _, _, state = await pair(app, cli)
            callback = await cli.get(CALLBACK, params={"code": code, "state": state})
            assert callback.headers["location"] == CONSENT
            assert set(writes) == {"verifying", "consent"}
            assert all(thread != threading.get_ident() for thread in writes.values())

    asyncio.run(run())
