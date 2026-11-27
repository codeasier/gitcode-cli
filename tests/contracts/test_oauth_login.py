"""Offline terminal/clean-browser/broker/vault composition, not live OAuth acceptance."""

from __future__ import annotations

import asyncio
import errno
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from functools import partial
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
            yield show
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

    def run(self, origin=ORIGIN, **extra):
        deps = {
            "_open_terminal": self.terminal,
            "_opener": self.open,
            "_store_factory": self.system,
            "_acquire": self.acquire,
        }
        return asyncio.run(login.login_with_browser(origin, **{**deps, **extra}))


@pytest.fixture
def flow(monkeypatch):
    return Flow(monkeypatch)


def test_real_client_real_store_injected_wire_and_storage(flow, capfd, caplog, monkeypatch, tmp_config_dir):
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

    acquire = partial(broker.acquire_receipt, _transport=httpx.MockTransport(serve))
    assert flow.run(_acquire=acquire) == WHO
    assert flow.events == ["tty", "system", "start", "open", "show", "redeem", "close", "verify", "put", "read"]
    assert seen == [("POST", ORIGIN + "/cli/v1/start"), ("POST", ORIGIN + "/cli/v1/redeem")]
    assert flow.browser == [ENTRY] and flow.tty == [PAIR]
    assert list(tmp_config_dir.iterdir()) == before
    assert capfd.readouterr() == ("", "") and PAIR not in caplog.text and TOKEN not in caplog.text


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
            raise asyncio.CancelledError
        errors = {"denied": AuthError(TOKEN), "unknown": OSError(TOKEN), "timeout": asyncio.TimeoutError(TOKEN)}
        raise errors[failure]

    with pytest.raises(asyncio.CancelledError if failure == "cancel" else AuthError) as err:
        flow.run(_acquire=fail)
    assert starts == [ORIGIN] and "verify" not in flow.events and "put" not in flow.events
    assert len(flow.browser) <= 1 and len(flow.tty) <= 1
    assert err.value.__context__ is None and TOKEN not in str(err.value)


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
            _store_factory=storage.OAuthCredentialStore.system, _open_terminal=lambda: nullcontext(flow.tty.append)
        )
    assert flow.events == [] and flow.browser == flow.tty == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX controlling terminal semantics")
def test_real_foreground_pty_keeps_pair_off_redirected_stdout():
    import pty

    master, slave = pty.openpty()
    # Allocate a new session/controlling tty in a fresh interpreter, not in
    # pytest itself. Use only an inert marker; no broker, browser or OS vault.
    code = """
import fcntl, os, termios
os.setsid()
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from gitcode_cli.oauth_login import _terminal
with _terminal() as show:
    show("synthetic-terminal-marker")
"""
    try:
        child = subprocess.run(
            [sys.executable, "-c", code], stdin=slave, stderr=slave, stdout=subprocess.PIPE, check=False, timeout=15
        )
    finally:
        os.close(slave)
    try:
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
        assert child.returncode == 0 and child.stdout == b""
        assert result.count(b"synthetic-terminal-marker") == 1
    finally:
        os.close(master)


def test_native_opener_forwards_only_url_to_registered_windows_handler(flow, monkeypatch):
    from types import SimpleNamespace

    launch = Mock()
    monkeypatch.setattr(login, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(login, "os", SimpleNamespace(startfile=launch))
    assert flow.run(_opener=login._open_browser) == WHO
    launch.assert_called_once_with(ENTRY, "open")
    assert flow.tty == [PAIR]
