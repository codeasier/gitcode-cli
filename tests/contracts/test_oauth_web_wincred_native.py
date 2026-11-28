"""Explicit Windows runner check; ordinary pytest never executes the WinCred smoke.

The installed Click entry point, HTTPS transport and Credential Manager are real.
The broker serves a synthetic transaction; no desktop, GitCode App or account is used.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import sysconfig
import threading
import time
from contextlib import ExitStack, contextmanager, nullcontext, suppress
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import distribution
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4


def _installed_entrypoint(checkout):
    from gitcode_cli import cli

    # Validate all installed Python source bytes, not only whatever file exposed the entry point.
    installed = Path(cli.__file__).resolve().parent
    purelib = Path(sysconfig.get_path("purelib")).resolve()
    source = checkout / "src" / "gitcode_cli"
    assert installed.is_relative_to(purelib) and not installed.is_relative_to(checkout)
    assert not Path.cwd().resolve().is_relative_to(checkout), "Smoke must run outside the source directory."

    def manifest(folder):
        return {p.relative_to(folder): hashlib.sha256(p.read_bytes()).digest() for p in folder.rglob("*.py")}

    files = manifest(installed)
    assert files and files == manifest(source), "Installed CLI bytes differ from checkout."
    (entry,) = distribution("pygitcode").entry_points.select(group="console_scripts", name="gitcode")
    assert entry.value == "gitcode_cli.cli:main" and entry.load() is cli.main
    launcher = Path(sysconfig.get_path("scripts")) / "gitcode.exe"
    result = subprocess.run([str(launcher), "auth", "login", "--help"], capture_output=True, check=True, timeout=10)
    assert b"--web" in result.stdout and b"--with-token" in result.stdout
    print(f"Installed wheel matches all {len(files)} CLI Python files, and installed launcher help works.")
    return entry.load()


def _certificate(root):
    openssl = shutil.which("openssl")
    assert openssl is not None, "The Windows TLS fixture requires OpenSSL."

    def run(*args):
        subprocess.run([openssl, *args], cwd=root, capture_output=True, check=True, timeout=20)

    run(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=Local Fixture CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
    )
    run(
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=fixture",
        "-keyout",
        "leaf.key",
        "-out",
        "leaf.csr",
    )
    (root / "leaf.ext").write_text(
        "basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n",
        encoding="ascii",
    )
    run(
        "x509",
        "-req",
        "-in",
        "leaf.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-days",
        "1",
        "-extfile",
        "leaf.ext",
        "-out",
        "leaf.pem",
    )
    return (root / "ca.pem").read_bytes()


def _proof_hash(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode("ascii")).digest()).decode("ascii").rstrip("=")


@contextmanager
def _broker(root, who, token, expiry):
    selector, pairing = (secrets.token_urlsafe(32) for _ in range(2))
    transactions = []
    challenge = None

    class Handler(BaseHTTPRequestHandler):
        timeout = 5

        def log_message(self, *args):
            pass

        def do_POST(self):  # noqa: N802 - stdlib HTTP handler name
            nonlocal challenge
            try:
                assert self.client_address[0] == "127.0.0.1" and isinstance(self.connection, ssl.SSLSocket)
                assert self.connection.version() in ("TLSv1.2", "TLSv1.3")
                assert self.headers["Host"] == authority and self.headers["Content-Type"] == "application/json"
                assert self.headers["Accept-Encoding"] == "identity"
                assert not {"authorization", "proxy-authorization", "cookie", "origin", "referer"} & {
                    k.lower() for k in self.headers
                }
                size = int(self.headers["Content-Length"])
                assert 0 < size <= 256
                body = json.loads(self.rfile.read(size))
                if self.path == "/cli/v1/start" and not transactions:
                    assert set(body) == {"challenge"} and re.fullmatch(r"[\w-]{43}", body["challenge"], re.ASCII)
                    challenge = body["challenge"]
                    status, reply = (
                        201,
                        {"selector": selector, "pairing": selector + "." + pairing, "browser_url": entry},
                    )
                elif self.path == "/cli/v1/redeem" and transactions == ["/cli/v1/start"]:
                    assert set(body) == {"selector", "verifier"} and body["selector"] == selector
                    assert _proof_hash(body["verifier"]) == challenge
                    status, reply = (
                        200,
                        {
                            "status": "authorized",
                            "access_token": token,
                            "subject": who.subject,
                            "login": who.login,
                            "expires_at": expiry,
                        },
                    )
                else:
                    raise ValueError("Unexpected broker request.")
            except (AssertionError, TypeError, ValueError):
                status, reply = 400, {"status": "unavailable"}
            else:
                transactions.append(self.path)
            raw = json.dumps(reply).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        host, port = server.server_address
        authority = f"{host}:{port}"
        origin = f"https://{authority}"
        entry = origin + "/cli/v1/browser"
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "leaf.pem", root / "leaf.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        worker.start()
        try:
            yield origin, selector + "." + pairing, transactions, (host, port)
        finally:
            server.shutdown()
            worker.join(3)
            assert not worker.is_alive(), "Local broker did not stop."


class _NonBrokerIOCPConnectError(AssertionError):
    """Raised by the guard, not by the OS or TCP handshake."""


def _is_exact_ipv4(sock, address, endpoint):
    return sock.family == socket.AF_INET and address == endpoint


def _guard_proactor_connect(stack, proactor_type, endpoint, native_hits):
    # Windows' asyncio numeric-IP path can call ConnectEx without invoking
    # socket.connect, socket.connect_ex or getaddrinfo. Check the real
    # proactor before it submits that operation, then call the original.
    original = proactor_type.connect

    def connect(proactor, sock, address):
        if not _is_exact_ipv4(sock, address, endpoint):
            raise _NonBrokerIOCPConnectError("Windows IOCP rejected a non-broker endpoint.")
        native_hits.append(address)
        return original(proactor, sock, address)

    stack.enter_context(patch.object(proactor_type, "connect", connect))


async def _probe_default_windows_proactor():
    loop = asyncio.get_running_loop()
    assert isinstance(loop, asyncio.ProactorEventLoop), "Expected the default Windows Proactor event loop."
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as outgoing,
    ):
        # Use a listening, local-only port, not a refused port or a real network
        # destination. A bypass would connect successfully instead of signaling.
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        outgoing.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(outgoing, listener.getsockname()), timeout=3)
        except _NonBrokerIOCPConnectError as exc:
            assert str(exc) == "Windows IOCP rejected a non-broker endpoint."
            return
        raise AssertionError("Default Windows asyncio connected without the required IOCP guard.")


@contextmanager
def _broker_network(endpoint):
    """Permit ordinary TCP/DNS only to the broker's exact IPv4 loopback endpoint."""
    # ProactorEventLoop uses one internal socketpair. Windows' stdlib may implement
    # it using a temporary loopback listener. Create that one pair before applying
    # the exact-endpoint restriction; transfer it once to asyncio, not to HTTP.
    first, second = socket.socketpair()
    available = True

    def take_pair():
        nonlocal available
        assert available, "Unexpected second asyncio socketpair."
        available = False
        return first, second

    def guard_network(method):
        def guarded(sock, address):
            assert _is_exact_ipv4(sock, address, endpoint), "Non-broker traffic was attempted."
            return method(sock, address)

        return guarded

    original_dns = socket.getaddrinfo

    def dns(host, port, *args, **kwargs):
        assert (host, port) == endpoint, "Non-broker DNS was attempted."
        return original_dns(host, port, *args, **kwargs)

    with first, second, ExitStack() as stack:
        stack.enter_context(patch.object(socket, "socketpair", take_pair))
        stack.enter_context(patch.object(socket, "getaddrinfo", dns))
        for method in ("connect", "connect_ex"):
            original = getattr(socket.socket, method)
            stack.enter_context(patch.object(socket.socket, method, guard_network(original)))
        native_hits = []
        if sys.platform == "win32":
            from asyncio.windows_events import IocpProactor

            _guard_proactor_connect(stack, IocpProactor, endpoint, native_hits)
        yield native_hits


def _value_digest(value):
    # The native backend writes this exact sequence of UTF-16LE bytes.
    return hashlib.sha256(value.encode("utf-16-le")).digest()


@contextmanager
def _credential_guard(native_backend, targets):
    # Capture the prospective value BEFORE put: the native API may commit then raise.
    # Digests remain in memory only and are never logged.
    attempts = {}

    def only_fixture(name, method):
        def guarded(backend, target, *args):
            assert target in targets, "Refusing to touch any non-fixture credential record."
            if name == "put":
                assert target not in attempts, "Unexpected retry of a native credential write."
                attempts[target] = _value_digest(args[0])
            return method(backend, target, *args)

        return guarded

    with ExitStack() as stack:
        for name in ("get", "put", "delete"):
            stack.enter_context(patch.object(native_backend, name, only_fixture(name, getattr(native_backend, name))))
        yield attempts


@contextmanager
def _proved_empty_slots(backend, targets, missing, attempts):
    def read(target):
        with suppress(missing):
            return backend.get(target)
        return None

    def settle(target):
        value = read(target)
        if value is None:
            return
        # Only a full-value match with this run's attempted write can be deleted.
        # WinCred has no CAS. This cannot isolate the interval between the read
        # and delete from a concurrent same-user writer; use random runner-only slots.
        assert attempts.get(target) == _value_digest(value), "Preserving an unmatched credential record."
        # A missing acknowledgement does not prove deletion failed. Never retry.
        with suppress(Exception):
            backend.delete(target)
        assert read(target) is None, "Native credential deletion was not confirmed."

    for target in targets:
        assert read(target) is None, "A synthetic WinCred target is not empty."
    try:
        yield
    finally:
        failures = 0
        for target in targets:
            try:
                settle(target)
            except Exception:
                failures += 1
        assert not failures, "Synthetic WinCred cleanup/readback failed; inspect the isolated runner."


class _MemoryMissingError(Exception):
    pass


class _MemoryBackend:
    """Ordinary offline tests exercise cleanup without invoking any OS credential API."""

    def __init__(self):
        self.records = {}
        self.calls = []
        self.lost_put_ack = None
        self.lost_delete_ack = None
        self.refused_delete = None

    def get(self, target):
        self.calls.append(("get", target))
        if target not in self.records:
            raise _MemoryMissingError
        return self.records[target]

    def put(self, target, value):
        self.calls.append(("put", target))
        self.records[target] = value
        if target == self.lost_put_ack:
            raise OSError("Put acknowledgement lost.")

    def delete(self, target):
        self.calls.append(("delete", target))
        if target == self.refused_delete:
            raise OSError("Delete did not commit.")
        del self.records[target]
        if target == self.lost_delete_ack:
            raise OSError("Delete acknowledgement lost.")


class TestSyntheticCleanup(TestCase):
    first, second = "synthetic-first", "synthetic-second"

    def setUp(self):
        self.backend = _MemoryBackend()
        self.targets = (self.first, self.second)

    @contextmanager
    def fixture(self):
        with (
            _credential_guard(_MemoryBackend, self.targets) as attempts,
            _proved_empty_slots(self.backend, self.targets, _MemoryMissingError, attempts),
        ):
            yield

    def test_unattempted_slot_acquired_during_run_is_preserved(self):
        with self.assertRaisesRegex(AssertionError, "cleanup/readback failed"), self.fixture():
            self.backend.put(self.first, "own")
            self.backend.records[self.second] = "different external value"
        self.assertEqual(self.backend.records, {self.second: "different external value"})
        self.assertIn(("delete", self.first), self.backend.calls)
        self.assertNotIn(("delete", self.second), self.backend.calls)

    def test_different_full_value_after_attempt_is_preserved(self):
        with self.assertRaisesRegex(AssertionError, "cleanup/readback failed"), self.fixture():
            self.backend.put(self.first, "inert")
            self.backend.put(self.second, "other own record")
            self.backend.records[self.first] = "inert☃"
        self.assertEqual(self.backend.records, {self.first: "inert☃"})
        self.assertNotIn(("delete", self.first), self.backend.calls)
        self.assertIn(("delete", self.second), self.backend.calls)

    def test_lost_put_ack_still_cleans_exact_own_value(self):
        self.backend.lost_put_ack = self.first
        with self.assertRaisesRegex(OSError, "Put acknowledgement lost"), self.fixture():
            self.backend.put(self.first, "own")
        self.assertEqual(self.backend.records, {})
        self.assertEqual(self.backend.calls.count(("put", self.first)), 1)
        self.assertEqual(self.backend.calls.count(("delete", self.first)), 1)
        self.assertIn(("get", self.first), self.backend.calls[self.backend.calls.index(("delete", self.first)) + 1 :])
        self.assertNotIn(("delete", self.second), self.backend.calls)

    def test_lost_delete_ack_is_reconciled_only_by_readback(self):
        self.backend.lost_delete_ack = self.first
        with self.fixture():
            self.backend.put(self.first, "own")
        self.assertEqual(self.backend.records, {})
        self.assertEqual(self.backend.calls.count(("delete", self.first)), 1)
        position = self.backend.calls.index(("delete", self.first))
        self.assertEqual(self.backend.calls[position + 1], ("get", self.first))

    def test_unconfirmed_delete_keeps_record_and_still_cleans_other(self):
        self.backend.refused_delete = self.first
        with self.assertRaisesRegex(AssertionError, "cleanup/readback failed"), self.fixture():
            self.backend.put(self.first, "own")
            self.backend.put(self.second, "other own record")
        self.assertEqual(self.backend.records, {self.first: "own"})
        self.assertEqual(self.backend.calls.count(("delete", self.first)), 1)
        position = self.backend.calls.index(("delete", self.first))
        self.assertEqual(self.backend.calls[position + 1], ("get", self.first))
        self.assertEqual(self.backend.calls[-2:], [("delete", self.second), ("get", self.second)])

    def test_preexisting_slot_leaves_both_slots_untouched(self):
        self.backend.records[self.second] = "existing isolated record"
        with self.assertRaisesRegex(AssertionError, "target is not empty"), self.fixture():
            self.fail("Preflight must refuse to enter.")
        self.assertEqual(self.backend.records, {self.second: "existing isolated record"})
        self.assertEqual(self.backend.calls, [("get", self.first), ("get", self.second)])

    def test_other_loopback_ports_and_second_socketpair_are_denied(self):
        with _broker_network(("127.0.0.1", 1234)):
            first, second = socket.socketpair()
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            with socket.socket() as sock, self.assertRaisesRegex(AssertionError, "Non-broker traffic"):
                sock.connect(("127.0.0.1", 1235))
            with self.assertRaisesRegex(AssertionError, "Non-broker DNS"):
                socket.getaddrinfo("127.0.0.1", 1235)
            with self.assertRaisesRegex(AssertionError, "Unexpected second asyncio socketpair"):
                socket.socketpair()

    def test_iocp_hook_blocks_before_native_call(self):
        calls = []

        class FakeProactor:
            def connect(self, sock, address):
                calls.append((sock.family, address))
                return "native-result"

        want = ("127.0.0.1", 1234)
        admitted = []
        with ExitStack() as guard, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            _guard_proactor_connect(guard, FakeProactor, want, admitted)
            proactor = FakeProactor()
            with self.assertRaisesRegex(_NonBrokerIOCPConnectError, "Windows IOCP rejected"):
                proactor.connect(sock, ("127.0.0.1", 1235))
            self.assertEqual(calls, [])
            self.assertEqual(proactor.connect(sock, want), "native-result")
            self.assertEqual(calls, [(socket.AF_INET, want)])
            self.assertEqual(admitted, [want])


def _exercise(entrypoint, root):
    from click.testing import CliRunner

    from gitcode_cli import cli, config, oauth_login
    from gitcode_cli import oauth_credential_store as credentials
    from gitcode_cli.oauth_account_selection import OAuthAccountSelection, OAuthAccountSelectionStore
    from gitcode_cli.oauth_account_selection import _target as selector_target
    from gitcode_cli.oauth_identity import OAuthIdentity

    ca = _certificate(root)
    who = OAuthIdentity("synthetic-gc-web-" + uuid4().hex, "SyntheticSmoke")
    token = "inert." + secrets.token_urlsafe(32)
    expiry = int(time.time()) + 120
    fixture_path = root / ("selector-" + uuid4().hex)
    namespace = PureWindowsPath(fixture_path)
    targets = (credentials._target(who), selector_target(namespace))
    assert len(set(targets)) == 2
    # Load only the Win32 API; this precheck must not use the write-capable command factory.
    backend = credentials._WindowsBackend(credentials._native_windows())

    opened, shown, verified = [], [], []
    terminal = oauth_login._TerminalSession(lambda: None, shown.append)

    def identity(access):
        assert access == token
        verified.append(True)
        return who

    native_login = oauth_login.login_with_browser

    async def guarded_login(origin, **kwargs):
        # The CLI owns this one asyncio.run; probe and real TLS share it and the
        # one pre-created socketpair. Never set an event-loop policy or fake IOCP.
        if sys.platform == "win32":
            await _probe_default_windows_proactor()
        return await native_login(origin, _open_terminal=lambda: nullcontext(terminal), _opener=opened.append, **kwargs)

    def no_pat(*_args, **_kwargs):
        raise AssertionError("The explicit OAuth entry accessed the PAT route.")

    proxy = "http://127.0.0.1:1"
    env = dict.fromkeys(("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"), proxy) | {
        "NO_PROXY": "",
        "SSLKEYLOGFILE": str(root / "unused-keylog"),
        "SSL_CERT_FILE": str(root / "nonexistent-ambient-ca"),
    }
    overrides = patch.multiple(config, CONFIG_DIR=fixture_path, CONFIG_PATH=fixture_path / "config.json")
    with (
        _credential_guard(credentials._WindowsBackend, targets) as attempts,
        _proved_empty_slots(backend, targets, credentials._MissingCredentialError, attempts),
    ):
        with (
            _broker(root, who, token, expiry) as (origin, pair, posts, endpoint),
            _broker_network(endpoint) as native_hits,
            overrides,
            patch.dict(os.environ, env),
            patch.object(cli, "get_token", no_pat),
            patch.object(config, "load_config", no_pat),
            patch.object(credentials, "verify_oauth_identity", identity),
            patch.object(oauth_login, "login_with_browser", guarded_login),
        ):
            result = CliRunner().invoke(
                entrypoint,
                [
                    "auth",
                    "login",
                    "--web",
                    "-h",
                    "gitcode.com",
                    "--broker-origin",
                    origin,
                    "--expected-login",
                    who.login,
                    "--broker-ca-sha256",
                    hashlib.sha256(ca).hexdigest(),
                    "--broker-ca-pem-base64",
                    base64.b64encode(ca).decode("ascii"),
                ],
                prog_name="gitcode",
            )
            assert result.exit_code == 0 and "account selection confirmed" in result.output
            assert all(x not in result.output for x in (token, pair, origin, who.subject, who.login))
            assert opened == [origin + "/cli/v1/browser"] and shown == [pair] and verified == [True]
            assert posts == ["/cli/v1/start", "/cli/v1/redeem"]
            if sys.platform == "win32":
                assert native_hits == [endpoint, endpoint], "Expected both real TLS connections to use guarded IOCP."

        observed = credentials.OAuthCredentialStore.system().read(who)
        selected = OAuthAccountSelectionStore.system(namespace).read()
        assert list(attempts) == list(targets), "Expected one credential write followed by one selector write."
        assert observed.access_token == token and observed.expires_at == expiry
        assert selected == OAuthAccountSelection(who.subject, who.login)
        assert json.loads(backend.get(targets[1])) == {"v": 1, "subject": who.subject, "login": who.login}
        assert not fixture_path.exists() and not (root / "unused-keylog").exists()


def _main():
    if (
        not __debug__
        or sys.platform != "win32"
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("GC_SYNTHETIC_WINCREDS_SMOKE") != "1"
    ):
        raise SystemExit("Run only in the dedicated GitHub-hosted Windows smoke; no native case was executed.")
    if any(name in os.environ for name in ("GC_TOKEN", "GC_GH_PROXY_ACTIVE")):
        raise SystemExit("Credential overrides or nested proxy are not allowed in the smoke.")
    try:
        checkout = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        entry = _installed_entrypoint(checkout)
        assert not any(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).cert_store_stats().values()), "Preseeded TLS store."
        with TemporaryDirectory(prefix="gc-web-native-", dir=os.environ["RUNNER_TEMP"]) as path:
            _exercise(entry, Path(path))
    except Exception as exc:
        # Only location/class (not argument, URL, token, platform exception, or record data).
        location = exc.__traceback__
        while location is not None and location.tb_next is not None:
            location = location.tb_next
        line = location.tb_lineno if location is not None else 0
        raise SystemExit(f"Synthetic native OAuth smoke failed ({type(exc).__name__}, line {line}).") from None
    print("Installed Windows OAuth entry completed native HTTPS, credential/selector readback and cleanup.")


if __name__ == "__main__":
    _main()
