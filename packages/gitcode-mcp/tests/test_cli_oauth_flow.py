import asyncio
import base64
import hashlib
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet

from gitcode_mcp import cli_oauth_flow as mod
from gitcode_mcp.cli_oauth_flow import CLIFlow, FlowRejected, Subject
from gitcode_mcp.oauth_store import OAuthStore, OAuthStoreError

TOKEN = "fixture-only-access-token.42"
WHO = Subject("a" * 24, "alice")


def verifier():
    return secrets.token_urlsafe(32)


def s256(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).rstrip(b"=").decode()


async def identity(token):
    assert token == TOKEN
    return WHO


def facade(store, verify=identity, **overrides):
    config = dict(broker_origin="https://broker.example", client_id="test-app")
    return CLIFlow(store, verify_identity=verify, **(config | overrides))


@pytest.fixture
def stores(tmp_path):
    key = Fernet.generate_key().decode()
    a, b = (OAuthStore(tmp_path / "broker.sqlite3", key) for _ in range(2))
    try:
        yield a, b
    finally:
        a.close()
        b.close()


def begin(flow):
    v = verifier()
    start = flow.create(s256(v))
    browser = flow.begin(start.selector, start.browser_start)
    return v, start, browser


def accepted(flow, allow=True):
    v, start, browser = begin(flow)
    claim = flow.claim_callback(start.selector, browser.cookie, browser.upstream_state)
    consent = asyncio.run(flow.complete_exchange(start.selector, claim, TOKEN, time.time() + 1000))
    assert consent.identity == WHO
    flow.decide(start.selector, browser.cookie, consent.csrf, allow=allow)
    return v, start.selector


def test_transitions_no_secret_leak_and_no_early_or_replayed_access(stores, caplog):
    caplog.set_level(logging.DEBUG)
    f = facade(stores[0])
    v, start, browser = begin(f)
    sid = start.selector
    with pytest.raises(FlowRejected):
        f.begin(sid, start.browser_start)
    for cookie, state in [(browser.cookie, verifier()), (verifier(), browser.upstream_state)]:
        with pytest.raises(FlowRejected):
            f.claim_callback(sid, cookie, state)
    claim = f.claim_callback(sid, browser.cookie, browser.upstream_state)
    with pytest.raises(FlowRejected):
        f.claim_callback(sid, browser.cookie, browser.upstream_state)
    with pytest.raises(FlowRejected):
        f.redeem(sid, v)
    with pytest.raises(FlowRejected):
        asyncio.run(
            f.complete_exchange(sid, mod.ExchangeClaim(verifier()), TOKEN, time.time() + 3600)
        )
    consent = asyncio.run(f.complete_exchange(sid, claim, TOKEN, time.time() + 3600))
    for cookie, csrf, allow in [
        (verifier(), consent.csrf, True),
        (browser.cookie, verifier(), False),
        (browser.cookie, consent.csrf, "allow"),
    ]:
        with pytest.raises(FlowRejected):
            f.decide(sid, cookie, csrf, allow=allow)
    with pytest.raises(FlowRejected):
        f.redeem(sid, v)
    disk = stores[0].path.read_bytes()
    f.decide(sid, browser.cookie, consent.csrf, allow=True)
    with pytest.raises(FlowRejected):
        f.decide(sid, browser.cookie, consent.csrf, allow=False)
    with pytest.raises(FlowRejected):
        f.redeem(sid, verifier())
    result = facade(stores[1]).redeem(sid, v)
    assert result.identity == WHO and result.access_token == TOKEN
    with pytest.raises(FlowRejected) as err:
        f.redeem(sid, v)
    for secret in (
        TOKEN,
        v,
        sid,
        start.browser_start,
        browser.cookie,
        browser.upstream_state,
        claim.proof,
        consent.csrf,
        WHO.login,
        WHO.subject,
    ):
        assert secret not in repr((start, browser, claim, consent, result, err.value)) + caplog.text
        assert secret.encode() not in disk


def test_denied_consumes_transaction(stores):
    f = facade(stores[0])
    v, sid = accepted(f, False)
    with pytest.raises(FlowRejected):
        f.redeem(sid, v)


@pytest.mark.parametrize(
    "override", [{"client_id": "other-app"}, {"broker_origin": "https://other.example"}]
)
def test_binding_rechecked_after_reopen(stores, override):
    f = facade(stores[0])
    bad = facade(stores[1], **override)
    t = f.create(s256(verifier()))
    with pytest.raises(FlowRejected):
        bad.begin(t.selector, t.browser_start)
    f.begin(t.selector, t.browser_start)


@pytest.mark.parametrize(
    "bad", [None, 42, b"123", "A" * 42, "A" * 42 + "B", "x" * 9000, "A" * 42 + "\n"]
)
def test_malformed_challenges_never_allocate(stores, bad):
    with pytest.raises(FlowRejected):
        facade(stores[0]).create(bad)


def test_cross_flow_proofs_never_authorize(stores):
    f = facade(stores[0])
    va, a, ab = begin(f)
    vb, b, bb = begin(f)
    with pytest.raises(FlowRejected):
        f.claim_callback(a.selector, bb.cookie, ab.upstream_state)
    with pytest.raises(FlowRejected):
        f.claim_callback(a.selector, ab.cookie, bb.upstream_state)
    ca = f.claim_callback(a.selector, ab.cookie, ab.upstream_state)
    cb = f.claim_callback(b.selector, bb.cookie, bb.upstream_state)
    with pytest.raises(FlowRejected):
        asyncio.run(f.complete_exchange(b.selector, ca, TOKEN, time.time() + 600))
    assert cb != ca and vb != va


def test_collision_and_capacity_dont_replace_active_transaction(tmp_path, monkeypatch):
    s = OAuthStore(tmp_path / "quota.db", Fernet.generate_key().decode(), max_pending_records=1)
    try:
        f = facade(s)
        start = f.create(s256(verifier()))
        with pytest.raises(OAuthStoreError, match="capacity"):
            f.create(s256(verifier()))
        with monkeypatch.context() as patch:
            patch.setattr(mod, "_nonce", lambda: start.selector)
            with pytest.raises(FlowRejected):
                f.create(s256(verifier()))
        f.begin(start.selector, start.browser_start)
    finally:
        s.close()


@pytest.mark.parametrize("shorten", [False, True])
def test_fixed_ttl_not_extended_and_no_redemption_of_expired_token(stores, monkeypatch, shorten):
    now = [time.time()]
    monkeypatch.setattr(time, "time", lambda: now[0])
    f = facade(stores[0])
    v, start, browser = begin(f)
    now[0] += 200
    c = f.claim_callback(start.selector, browser.cookie, browser.upstream_state)
    token_ttl = 1 if shorten else 3600
    form = asyncio.run(f.complete_exchange(start.selector, c, TOKEN, now[0] + token_ttl))
    f.decide(start.selector, browser.cookie, form.csrf, allow=True)
    now[0] += 1 if shorten else 100
    with pytest.raises(FlowRejected):
        facade(stores[1]).redeem(start.selector, v)


@pytest.mark.parametrize("outcome", ["echo-error", "empty-subject", "token-in-login", "wrong-type"])
def test_failed_independent_verification_never_stages_credentials(stores, outcome, caplog):
    seen = []

    async def verify(token):
        seen.append(token)
        if outcome == "echo-error":
            raise RuntimeError("sensitive: " + token)
        return {
            "empty-subject": Subject("", "name"),
            "token-in-login": Subject("1", token),
            "wrong-type": ("1", "name"),
        }[outcome]

    f = facade(stores[0], verify)
    v, start, browser = begin(f)
    c = f.claim_callback(start.selector, browser.cookie, browser.upstream_state)
    for _ in range(2):
        with pytest.raises(FlowRejected) as err:
            asyncio.run(f.complete_exchange(start.selector, c, TOKEN, time.time() + 3600))
        assert TOKEN not in repr(err.value) + caplog.text and err.value.__context__ is None
    assert seen == [TOKEN]
    with pytest.raises(FlowRejected):
        f.redeem(start.selector, v)


@pytest.mark.parametrize(
    "token, expiry",
    [
        (TOKEN + "\n", None),
        (None, None),
        (TOKEN, "3600"),
        (TOKEN, False),
        (TOKEN, float("nan")),
        (TOKEN, float("inf")),
        (TOKEN, 1),
        (TOKEN, 10**900),
    ],
)
def test_malformed_exchange_never_calls_identity(stores, token, expiry):
    async def never(_):
        pytest.fail("malformed exchange called verifier")

    f = facade(stores[0], never)
    _, start, b = begin(f)
    c = f.claim_callback(start.selector, b.cookie, b.upstream_state)
    with pytest.raises(FlowRejected):
        asyncio.run(
            f.complete_exchange(
                start.selector, c, token, time.time() + 600 if expiry is None else expiry
            )
        )


def test_verifier_runs_without_holding_transaction_and_expiry_rechecked(stores, monkeypatch):
    now = [time.time()]
    monkeypatch.setattr(time, "time", lambda: now[0])

    async def verify(token):
        # Same-connection nested transactions would fail; force expiry while
        # suspended, as a slow /user response near the deadline might do.
        with stores[0].transaction():
            pass
        await asyncio.sleep(0)
        now[0] += 300
        return WHO

    f = facade(stores[0], verify)
    _, s, b = begin(f)
    c = f.claim_callback(s.selector, b.cookie, b.upstream_state)
    with pytest.raises(FlowRejected):
        asyncio.run(f.complete_exchange(s.selector, c, TOKEN, now[0] + 1000))


def race(stores, action):
    barrier = threading.Barrier(2)

    def call(store):
        f = facade(store)
        barrier.wait(timeout=5)
        try:
            return action(f)
        except FlowRejected:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(call, stores))
    assert results.count(None) == 1
    return next(v for v in results if v is not None)


def test_only_one_winner_per_phase_across_independent_connections(stores):
    v = verifier()
    s = facade(stores[0]).create(s256(v))
    sid = s.selector
    b = race(stores, lambda f: f.begin(sid, s.browser_start))
    c = race(stores, lambda f: f.claim_callback(sid, b.cookie, b.upstream_state))
    form = race(
        stores, lambda f: asyncio.run(f.complete_exchange(sid, c, TOKEN, time.time() + 600))
    )

    def allow(f):
        f.decide(sid, b.cookie, form.csrf, allow=True)
        return True

    race(stores, allow)
    assert race(stores, lambda f: f.redeem(sid, v)).access_token == TOKEN
