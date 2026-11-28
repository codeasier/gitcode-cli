"""Offline terminal/clean-browser/broker/vault composition, not live OAuth acceptance."""

from __future__ import annotations

import asyncio
import errno
import json
import os
import ssl
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from functools import partial
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from gitcode_cli import oauth_broker_client as broker
from gitcode_cli import oauth_credential_store as storage
from gitcode_cli import oauth_login as login
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_identity import OAuthIdentity

ORIGIN = "https://broker.invalid"
ENTRY = ORIGIN + "/cli/v1/browser"
PAIR = "A" * 43 + "." + "B" * 42 + "A"
TOKEN = "inert.synthetic.token"
WHO = OAuthIdentity("opaque01", "fixture-user")

# Synthetic self-signed CA for SSLContext inspection only. No private key or TLS socket.
BROKER_CA = """-----BEGIN CERTIFICATE-----
MIIBbTCCAR+gAwIBAgIUSfQLhEEVJOQeMzLNKXsFVV30AlkwBQYDK2VwMCQxIjAg
BgNVBAMMGVRlc3QtT25seS1PQXV0aC1Ccm9rZXItQ0EwHhcNMjYxMTI4MDAyNjIz
WhcNMzYxMTI1MDAyNjIzWjAkMSIwIAYDVQQDDBlUZXN0LU9ubHktT0F1dGgtQnJv
a2VyLUNBMCowBQYDK2VwAyEAXxF5XIXSBwFJv8ETekNLCa5vfC7yMJJL7e6iv3fn
+vujYzBhMB0GA1UdDgQWBBQG7imNrElaSDhbQxHwwiZY7X7rKzAfBgNVHSMEGDAW
gBQG7imNrElaSDhbQxHwwiZY7X7rKzAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB
/wQEAwIBBjAFBgMrZXADQQASedacGuSwz3mHg5ka95/PrNqI+11Bd4hZ+nNTsZhM
7R8zHupheuDPBahYN1VNk2uVMxyYg8SvxldBKY/3cC4A
-----END CERTIFICATE-----
"""


def receipt():
    return broker.BrokerReceipt(TOKEN, WHO.subject, WHO.login, time.time() + 120)


class Vault:
    def __init__(self, events):
        self.events = events
        self.value = None

    def put(self, _key, value):
        self.events.append("put")
        self.value = value

    def get(self, _key):
        self.events.append("read")
        return self.value

    def delete(self, _key):
        pytest.fail("must not mutate an uncertain credential")


class Wire(httpx.AsyncByteStream):
    def __init__(self, obj):
        self.buf = json.dumps(obj).encode("ascii")

    async def __aiter__(self):
        yield self.buf


class Flow:
    def __init__(self, monkeypatch):
        self.events = []
        self.browser = []
        self.tty = []
        self.native = Vault(self.events)
        self.vault = storage.OAuthCredentialStore(self.native)
        self.who = WHO

        def verify(token):
            assert token == TOKEN
            self.events.append("verify")
            return self.who

        monkeypatch.setattr(storage, "verify_oauth_identity", verify)

    def system(self):
        self.events.append("system")
        return self.vault

    @contextmanager
    def terminal(self):
        self.events.append("tty")

        def show(pair):
            self.tty.append(pair)
            self.events.append("show")

        try:
            yield login._TerminalSession(lambda: None, show)
        finally:
            self.events.append("close")

    def open(self, url):
        self.browser.append(url)
        self.events.append("open")

    async def acquire(self, origin, present):
        assert origin == ORIGIN
        self.events.append("start")
        await present(ENTRY, PAIR)
        self.events.append("redeem")
        return receipt()

    def run(self, origin=ORIGIN, *, native_acquire=False, **extra):
        deps = {
            "_open_terminal": self.terminal,
            "_opener": self.open,
            "_store_factory": self.system,
        }
        if not native_acquire:
            deps["_acquire"] = self.acquire
        return asyncio.run(login.login_with_browser(origin, **{**deps, **extra}))


@pytest.fixture
def flow(monkeypatch):
    return Flow(monkeypatch)


def _observe_native_transport(monkeypatch, transport, *, explicit):
    def native_transport(*, verify, trust_env, retries):
        assert verify.verify_mode == ssl.CERT_REQUIRED and verify.check_hostname
        assert not trust_env and retries == 0
        roots = verify.get_ca_certs(binary_form=True)
        expected = ssl.PEM_cert_to_DER_cert(BROKER_CA)
        if explicit:
            assert roots == [expected]
            assert not verify.hostname_checks_common_name
        else:
            assert roots and expected not in roots
        return transport

    factory = Mock(side_effect=native_transport)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    return factory


@pytest.mark.parametrize("mode", ["injected", "public-ca", "explicit-ca", "wrong-expected-login"])
def test_real_client_real_store_wire_and_storage(flow, capfd, caplog, monkeypatch, tmp_config_dir, mode):
    monkeypatch.setenv("BROWSER", "this must never run")
    monkeypatch.setenv("GC_TOKEN", "unrelated.fake.pat")
    before = list(tmp_config_dir.iterdir())
    seen = []

    def serve(req):
        seen.append((req.method, str(req.url)))
        if req.url.path == "/cli/v1/start":
            flow.events.append("start")
            obj = {"browser_url": ENTRY, "selector": PAIR[:43], "pairing": PAIR}
            status = 201
        else:
            assert req.url.path == "/cli/v1/redeem"
            flow.events.append("redeem")
            obj = {"status": "authorized", **vars(receipt())}
            status = 200
        return httpx.Response(
            status, headers={"cache-control": "no-store", "content-type": "application/json"}, stream=Wire(obj)
        )

    transport = httpx.MockTransport(serve)
    if mode == "injected":
        acquire = partial(broker.acquire_receipt, _transport=transport)
        assert flow.run(_acquire=acquire) == WHO
    else:
        factory = _observe_native_transport(monkeypatch, transport, explicit=mode != "public-ca")
        options = {"native_acquire": True}
        if mode != "public-ca":
            options["broker_trust"] = broker.BrokerTrust(ORIGIN, BROKER_CA)
            if any(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).cert_store_stats().values()):
                # A preseeded runtime cannot offer an explicit-CA-only store.
                with pytest.raises(AuthError):
                    flow.run(expected_login=WHO.login, **options)
                assert flow.events == ["tty", "system", "close"]
                assert not seen and flow.browser == flow.tty == [] and flow.native.value is None
                factory.assert_not_called()
                return
        if mode == "wrong-expected-login":
            with pytest.raises(AuthError) as err:
                flow.run(expected_login=WHO.login.upper(), **options)
            assert str(err.value) == str(login._failed()) and err.value.__context__ is None
            assert flow.native.value is None
        else:
            assert flow.run(expected_login=WHO.login, **options) == WHO
        factory.assert_called_once()

    events = ["tty", "system", "start", "open", "show", "redeem", "close"]
    if mode != "wrong-expected-login":
        events += ["verify", "put", "read"]
    assert flow.events == events
    assert seen == [("POST", ORIGIN + "/cli/v1/start"), ("POST", ORIGIN + "/cli/v1/redeem")]
    assert flow.browser == [ENTRY] and flow.tty == [PAIR]
    assert list(tmp_config_dir.iterdir()) == before
    assert capfd.readouterr() == ("", "") and PAIR not in caplog.text and TOKEN not in caplog.text


@pytest.mark.parametrize("kind", ["different-host", "different-port", "untyped", "bad-origin-type", "custom-acquire"])
def test_rejects_explicit_broker_trust_before_opening_terminal(flow, monkeypatch, kind):
    native_transport = Mock(side_effect=AssertionError("network construction after a failed preflight"))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", native_transport)
    trust = {
        "different-host": broker.BrokerTrust("https://other.invalid", BROKER_CA),
        "different-port": broker.BrokerTrust(ORIGIN + ":8443", BROKER_CA),
        "untyped": {"origin": ORIGIN, "ca_pem": BROKER_CA},
        "bad-origin-type": broker.BrokerTrust(None, BROKER_CA),
        "custom-acquire": broker.BrokerTrust(ORIGIN, BROKER_CA),
    }[kind]
    acquire = Mock(side_effect=AssertionError("must not call injected acquisition with explicit trust"))
    overrides = {"_acquire": acquire} if kind == "custom-acquire" else {}
    with pytest.raises(AuthError) as err:
        flow.run(native_acquire=True, broker_trust=trust, **overrides)
    assert str(err.value) == str(login._failed()) and err.value.__context__ is None
    assert flow.events == [] and flow.browser == flow.tty == [] and flow.native.value is None
    native_transport.assert_not_called()
    acquire.assert_not_called()


def test_same_origin_malformed_ca_fails_in_real_acquisition_without_fallback(flow, monkeypatch):
    transport = Mock(side_effect=AssertionError("must not construct transport after invalid CA"))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    with pytest.raises(AuthError) as err:
        flow.run(native_acquire=True, broker_trust=broker.BrokerTrust(ORIGIN, "invalid CA fixture"))
    assert str(err.value) == str(login._failed()) and err.value.__context__ is None
    assert flow.events == ["tty", "system", "close"] and flow.browser == flow.tty == [] and flow.native.value is None
    transport.assert_not_called()


@pytest.mark.parametrize("failure", ["origin", "terminal", "store", "no-store"])
def test_preflight_does_not_launch_or_contact(flow, failure):
    exc = RuntimeError(TOKEN)
    options = {
        "origin": {"origin": "https://broker.invalid/path"},
        "terminal": {"_open_terminal": Mock(side_effect=exc)},
        "store": {"_store_factory": Mock(side_effect=exc)},
        "no-store": {"_store_factory": lambda: None},
    }
    with pytest.raises(AuthError) as err:
        flow.run(**options[failure])
    assert err.value.__context__ is None and TOKEN not in str(err.value)
    assert "start" not in flow.events and flow.browser == flow.tty == []


@pytest.mark.parametrize(
    ("url", "pair"),
    [
        (ENTRY + "?pair=secret", PAIR),
        ("https://other.invalid/cli/v1/browser", PAIR),
        (ENTRY, PAIR[:-1] + "\n"),
        (ENTRY, "A" * 43 + "." + "A" * 43),
        (ENTRY, "unsafe"),
        (ENTRY, PAIR[:43] + "." + "B" * 43),
    ],
)
def test_injected_presentation_still_requires_exact_url_and_safe_pair(flow, url, pair):
    async def invalid(origin, present):
        # Even if a broken transport suppresses presentation failure, don't save.
        with pytest.raises(AuthError):
            await present(url, pair)
        return receipt()

    with pytest.raises(AuthError):
        flow.run(_acquire=invalid)
    assert flow.tty == flow.browser == [] and "verify" not in flow.events


@pytest.mark.parametrize("failure", ["skip", "twice", "untyped", "denied", "unknown", "timeout", "cancel"])
def test_no_second_transaction_and_no_save(flow, failure):
    starts = []

    async def fail(origin, present):
        starts.append(origin)
        if failure == "skip":
            return receipt()
        await present(ENTRY, PAIR)
        if failure == "twice":
            with pytest.raises(AuthError):
                await present(ENTRY, PAIR)
            return receipt()
        if failure == "untyped":
            return vars(receipt())
        if failure == "cancel":
            try:
                raise RuntimeError(PAIR)
            except RuntimeError as exc:
                raise asyncio.CancelledError(TOKEN) from exc
        errors = {"denied": AuthError(TOKEN), "unknown": OSError(TOKEN), "timeout": asyncio.TimeoutError(TOKEN)}
        raise errors[failure]

    with pytest.raises(asyncio.CancelledError if failure == "cancel" else AuthError) as err:
        flow.run(_acquire=fail)
    assert starts == [ORIGIN] and "verify" not in flow.events and "put" not in flow.events
    assert len(flow.browser) <= 1 and len(flow.tty) <= 1
    if failure == "cancel":
        assert_opaque_cancellation(err.value)
    else:
        assert err.value.__context__ is None and TOKEN not in str(err.value)


def assert_opaque_cancellation(exc):
    # Python 3.9/3.10 Task.result() may wrap the coroutine's CancelledError in
    # another one. Check the entire chain; a hidden sensitive cause also fails.
    while exc is not None:
        assert type(exc) is asyncio.CancelledError and not exc.args
        assert exc.__cause__ is None
        exc = exc.__context__


def test_cancellation_is_sanitized_at_coroutine_boundary(flow):
    async def acquire(origin, present):
        await present(ENTRY, PAIR)
        raise asyncio.CancelledError(TOKEN) from RuntimeError(PAIR)

    async def check():
        with pytest.raises(asyncio.CancelledError) as err:
            await login.login_with_browser(
                ORIGIN, _open_terminal=flow.terminal, _opener=flow.open, _acquire=acquire, _store_factory=flow.system
            )
        assert_opaque_cancellation(err.value)
        # Direct await has no Task wrapper: the original exception was discarded.
        assert err.value.__context__ is None

    asyncio.run(check())
    assert "verify" not in flow.events and "put" not in flow.events


def test_queued_cancellation_at_receipt_does_not_save(flow):
    async def acquire(origin, present):
        await present(ENTRY, PAIR)
        asyncio.get_running_loop().call_soon(asyncio.current_task().cancel)
        return receipt()

    with pytest.raises(asyncio.CancelledError):
        flow.run(_acquire=acquire)
    assert "verify" not in flow.events and "put" not in flow.events


def test_no_second_presentation_after_acquisition_returns(flow):
    captured = []

    async def acquire(origin, present):
        captured.append(present)
        await present(ENTRY, PAIR)
        return receipt()

    assert flow.run(_acquire=acquire) == WHO
    with pytest.raises(AuthError):
        asyncio.run(captured[0](ENTRY, PAIR))
    assert flow.tty == [PAIR] and flow.browser == [ENTRY]


def test_opener_failure_never_shows_or_persists(flow, capfd):
    opener = Mock(side_effect=RuntimeError(PAIR))
    with pytest.raises(AuthError) as err:
        flow.run(_opener=opener)
    opener.assert_called_once_with(ENTRY)
    assert flow.tty == [] and "redeem" not in flow.events and "put" not in flow.events
    assert err.value.__context__ is None and PAIR not in str(err.value) and capfd.readouterr() == ("", "")


def test_nonmatching_identity_never_put(flow):
    flow.who = OAuthIdentity(WHO.subject, "impostor")
    with pytest.raises(AuthError):
        flow.run()
    assert flow.events.count("verify") == 1 and "put" not in flow.events


def test_expected_login_commits_with_exact_verified_spelling(flow):
    flow.who = OAuthIdentity(WHO.subject, "Fixture-User.X_42")

    async def acquire(origin, present):
        return replace(await flow.acquire(origin, present), login=flow.who.login)

    assert flow.run(expected_login=flow.who.login, _acquire=acquire) == flow.who
    assert flow.events == ["tty", "system", "start", "open", "show", "redeem", "close", "verify", "put", "read"]
    assert json.loads(flow.native.value)[3] == flow.who.login


@pytest.mark.parametrize("expected", ["", ".", "..", "wrong/name", " user ", "user\n", "界", "a" * 256, True, 123])
def test_invalid_expected_login_fails_before_any_terminal_or_contact(flow, expected, capfd):
    with pytest.raises(AuthError) as err:
        flow.run(expected_login=expected)
    assert flow.events == [] and flow.native.value is None and flow.browser == flow.tty == []
    assert str(err.value) == str(login._failed()) and err.value.__context__ is None
    assert capfd.readouterr() == ("", "")


@pytest.mark.parametrize(
    ("expected", "verified_identity", "verify_count"),
    [
        ("unrelated-user", WHO, 0),
        (WHO.login.upper(), WHO, 0),
        (WHO.login, OAuthIdentity(WHO.subject, WHO.login.upper()), 1),
        (WHO.login, OAuthIdentity("different-subject", WHO.login), 1),
    ],
)
def test_expected_login_requires_receipt_and_verified_identity_before_vault(
    flow, expected, verified_identity, verify_count
):
    flow.who = verified_identity
    flow.native.value = "pre-existing record"
    with pytest.raises(AuthError) as err:
        flow.run(expected_login=expected)
    assert str(err.value) == str(login._failed()) and err.value.__context__ is None
    assert flow.events.count("start") == flow.events.count("redeem") == 1
    assert flow.events.count("verify") == verify_count
    assert not {"put", "read"} & set(flow.events) and flow.native.value == "pre-existing record"


def test_uncertain_native_write_never_retries_or_deletes(flow, monkeypatch):
    def corrupt(key):
        flow.events.append("failed-read")
        raise OSError(TOKEN)

    monkeypatch.setattr(flow.native, "get", corrupt)
    with pytest.raises(AuthError) as err:
        flow.run()
    assert flow.events.count("start") == flow.events.count("redeem") == flow.events.count("put") == 1
    assert flow.events[-1] == "failed-read" and flow.native.value is not None
    assert err.value.__context__ is None and TOKEN not in str(err.value)


def test_real_terminal_default_rejects_noninteractive_before_start(flow, monkeypatch):
    monkeypatch.setattr(os, "isatty", lambda fd: False)
    with pytest.raises(AuthError):
        flow.run(_open_terminal=login._terminal)
    assert flow.events == [] and flow.browser == []


@pytest.mark.skipif(sys.platform == "win32", reason="Linux/macOS have no supported native vault")
def test_unsupported_system_vault_precedes_browser_and_redeem(flow):
    with pytest.raises(AuthError):
        flow.run(
            _store_factory=storage.OAuthCredentialStore.system,
            _open_terminal=lambda: nullcontext(login._TerminalSession(lambda: None, flow.tty.append)),
        )
    assert flow.events == [] and flow.browser == flow.tty == []


def run_in_controlling_pty(code):
    import pty

    master, slave = pty.openpty()
    setup = """
import fcntl, os, signal, termios
os.setsid()
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
"""
    try:
        try:
            child = subprocess.run(
                [sys.executable, "-c", setup + code],
                stdin=slave,
                stderr=slave,
                stdout=subprocess.PIPE,
                check=False,
                timeout=15,
            )
        finally:
            os.close(slave)
        result = bytearray()
        while True:
            try:
                chunk = os.read(master, 4096)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            result.extend(chunk)
        return child, result
    finally:
        os.close(master)


@pytest.mark.skipif(os.name != "posix", reason="POSIX controlling terminal semantics")
def test_real_foreground_pty_keeps_pair_off_redirected_stdout():
    child, terminal = run_in_controlling_pty("""
from gitcode_cli.oauth_login import _terminal
with _terminal() as terminal:
    terminal.show("synthetic-terminal-marker")
""")
    assert child.returncode == 0 and child.stdout == b""
    assert terminal.count(b"synthetic-terminal-marker") == 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX controlling terminal semantics")
@pytest.mark.parametrize("phase", ["before-open", "after-open"])
def test_real_pty_loses_foreground_and_does_not_show_pair(phase):
    # A second process group in the same session takes the real PTY's
    # foreground. Use a fake opener, fake acquisition and no native vault.
    child, terminal = run_in_controlling_pty(f"""
import asyncio
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_login import _Presentation, _terminal
pg = os.fork()
if pg == 0:
    signal.pause()
    os._exit(0)
try:
    os.setpgid(pg, pg)
    launches = []

    def background():
        os.tcsetpgrp(0, pg)
        assert os.tcgetpgrp(0) == pg

    def open_browser(url):
        launches.append(url)
        if {phase!r} == "after-open":
            background()

    with _terminal() as terminal:
        presentation = _Presentation({ENTRY!r}, terminal, open_browser)
        if {phase!r} == "before-open":
            background()
        try:
            asyncio.run(presentation.present({ENTRY!r}, {PAIR!r}))
        except AuthError:
            if presentation.completed:
                raise AssertionError("invalid success")
        else:
            raise AssertionError("background presentation succeeded")
    print(len(launches))
finally:
    os.kill(pg, signal.SIGKILL)
    os.waitpid(pg, 0)
""")
    assert (child.returncode, child.stdout) == (0, b"0\n" if phase == "before-open" else b"1\n")
    assert PAIR.encode("ascii") not in terminal and b"one-time pairing" not in terminal


def test_native_opener_forwards_only_url_to_registered_windows_handler(flow, monkeypatch):
    from types import SimpleNamespace

    launch = Mock()
    monkeypatch.setattr(login, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(login, "os", SimpleNamespace(startfile=launch))
    assert flow.run(_opener=login._open_browser) == WHO
    launch.assert_called_once_with(ENTRY, "open")
    assert flow.tty == [PAIR]


def test_pending_identity_check_does_not_block_event_loop_and_cannot_commit(flow, monkeypatch):
    entered, released = Event(), Event()

    def verifier(token):
        assert token == TOKEN
        entered.set()
        if not released.wait(3):
            raise AssertionError("event loop could not cancel during verification")
        return WHO

    monkeypatch.setattr(storage, "verify_oauth_identity", verifier)

    async def scenario():
        task = asyncio.create_task(
            login.login_with_browser(
                ORIGIN,
                _open_terminal=flow.terminal,
                _opener=flow.open,
                _acquire=flow.acquire,
                _store_factory=flow.system,
            )
        )
        try:
            # A call from a second thread here might mask event-loop blockage.
            # The same loop must actually run while the verifier is paused.
            while not entered.is_set() and not task.done():
                await asyncio.sleep(0)
            assert not task.done() and entered.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as err:
                await task
            assert_opaque_cancellation(err.value)
        finally:
            released.set()

    asyncio.run(scenario())
    assert flow.events.count("start") == flow.events.count("redeem") == 1
    assert flow.native.value is None and not set(flow.events) & {"put", "read"}


@pytest.mark.parametrize("expected_login", [None, WHO.login])
def test_genuine_task_cancel_at_verified_identity_boundary(flow, monkeypatch, expected_login):
    verified, ready_to_return = Event(), Event()
    prepare = storage.OAuthCredentialStore._prepare

    async def scenario():
        loop = asyncio.get_running_loop()

        def signal_verified(store, **claimed):
            prepared = prepare(store, **claimed)
            # This executes after /user succeeded, but before the verified receipt
            # is delivered to the loop. Queue real Task.cancel(), not a fake error.
            verified.set()
            loop.call_soon_threadsafe(task.cancel)
            ready_to_return.set()
            return prepared

        monkeypatch.setattr(storage.OAuthCredentialStore, "_prepare", signal_verified)
        task = asyncio.create_task(
            login.login_with_browser(
                ORIGIN,
                expected_login=expected_login,
                _open_terminal=flow.terminal,
                _opener=flow.open,
                _acquire=flow.acquire,
                _store_factory=flow.system,
            )
        )
        with pytest.raises(asyncio.CancelledError):
            await task
        assert verified.is_set()

    asyncio.run(scenario())
    assert ready_to_return.is_set()
    assert flow.events.count("verify") == 1 and flow.native.value is None
    assert not set(flow.events) & {"put", "read"}


def test_identity_wait_deadline_never_commits_late_verification(flow, monkeypatch):
    entered, released = Event(), Event()

    def verifier(token):
        entered.set()
        if not released.wait(3):
            raise AssertionError("deadline did not run while verifier was pending")
        return WHO

    monkeypatch.setattr(storage, "verify_oauth_identity", verifier)
    monkeypatch.setattr(login, "_IDENTITY_WAIT_SECONDS", 0.1)

    async def scenario():
        try:
            with pytest.raises(AuthError):
                await login.login_with_browser(
                    ORIGIN,
                    _open_terminal=flow.terminal,
                    _opener=flow.open,
                    _acquire=flow.acquire,
                    _store_factory=flow.system,
                )
        finally:
            released.set()

    asyncio.run(scenario())
    assert entered.is_set() and flow.native.value is None
    assert not set(flow.events) & {"put", "read"}
