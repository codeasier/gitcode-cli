"""Offline tests at the actual Click entry point; no provider or native vault access."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import socket
import ssl
import time
from contextlib import nullcontext
from functools import partial
from pathlib import PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from gitcode_cli import cli, oauth_broker_client, oauth_credential_store, oauth_login, oauth_web_inputs
from gitcode_cli.commands import auth
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_account_selection import OAuthAccountSelectionStore
from gitcode_cli.oauth_identity import OAuthIdentity

ORIGIN = "https://broker.example.invalid:8443"
WHO = OAuthIdentity("opaque-subject", "Exact.Login")
FIXTURE_TOKEN = "inert.not.a.production.token"
PRIVATE = "must-not-echo-this-value"
PAIR = "A" * 43 + "." + "B" * 42 + "A"

# Synthetic public CA only; no private key or TLS server.
CA = b"""-----BEGIN CERTIFICATE-----
MIIBbTCCAR+gAwIBAgIUSfQLhEEVJOQeMzLNKXsFVV30AlkwBQYDK2VwMCQxIjAg
BgNVBAMMGVRlc3QtT25seS1PQXV0aC1Ccm9rZXItQ0EwHhcNMjYxMTI4MDAyNjIz
WhcNMzYxMTI1MDAyNjIzWjAkMSIwIAYDVQQDDBlUZXN0LU9ubHktT0F1dGgtQnJv
a2VyLUNBMCowBQYDK2VwAyEAXxF5XIXSBwFJv8ETekNLCa5vfC7yMJJL7e6iv3fn
+vujYzBhMB0GA1UdDgQWBBQG7imNrElaSDhbQxHwwiZY7X7rKzAfBgNVHSMEGDAW
gBQG7imNrElaSDhbQxHwwiZY7X7rKzAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB
/wQEAwIBBjAFBgMrZXADQQASedacGuSwz3mHg5ka95/PrNqI+11Bd4hZ+nNTsZhM
7R8zHupheuDPBahYN1VNk2uVMxyYg8SvxldBKY/3cC4A
-----END CERTIFICATE-----
""".replace(b"\n", b"\r\n")
PEM = base64.b64encode(CA).decode("ascii")
FINGERPRINT = hashlib.sha256(CA).hexdigest().upper()


def flags(**overrides):
    options = {
        "broker-origin": ORIGIN,
        "expected-login": WHO.login,
        "broker-ca-sha256": FINGERPRINT,
        "broker-ca-pem-base64": PEM,
        **overrides,
    }
    return [f"--{key}={value}" for key, value in options.items() if value is not None]


def run(*args, root=(), **kwargs):
    return CliRunner().invoke(cli.main, [*root, *args], prog_name="gc", **kwargs)


def forbidden(*_args, **_kwargs):
    pytest.fail("accessed a prohibited credential or network path")


@pytest.fixture(autouse=True)
def sandbox(tmp_config_dir, monkeypatch):
    monkeypatch.delenv("GC_TOKEN", raising=False)
    monkeypatch.delenv("GC_GH_PROXY_ACTIVE", raising=False)
    # Windows asyncio's socketpair fallback can require a local connection.
    original_dns = socket.getaddrinfo

    def local_dns(host, *args, **kwargs):
        if host not in (None, "localhost", "127.0.0.1", "::1"):
            forbidden(host)
        return original_dns(host, *args, **kwargs)

    def guard(method):
        def local_connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1"):
                forbidden(address)
            return method(sock, address)

        return local_connect

    monkeypatch.setattr(socket, "getaddrinfo", local_dns)
    monkeypatch.setattr(socket.socket, "connect", guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(socket.socket.connect_ex))
    return tmp_config_dir


@pytest.fixture
def no_pat(monkeypatch):
    monkeypatch.setattr(cli, "get_token", forbidden)
    monkeypatch.setattr(auth, "get_token", forbidden)
    monkeypatch.setattr(auth, "load_config", forbidden)
    monkeypatch.setattr(auth.config, "load_config", forbidden)
    monkeypatch.setattr(auth, "edit_accounts", forbidden)
    monkeypatch.setattr(auth, "_verified_login", forbidden)
    monkeypatch.setattr(auth.click, "prompt", forbidden)


@pytest.fixture
def win(monkeypatch):
    # Set only the command's platform guard. Never invoke real Win32 APIs.
    monkeypatch.setattr(auth, "sys", SimpleNamespace(platform="win32"))


@pytest.fixture
def trusted_context():
    if any(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).cert_store_stats().values()):
        pytest.skip("runtime pre-seeds private broker TLS stores and rejects explicit trust")


def assert_clean(result):
    assert result.exception is None or isinstance(result.exception, SystemExit)
    for secret in (PRIVATE, FIXTURE_TOKEN, ORIGIN, PEM, FINGERPRINT, PAIR, WHO.login, WHO.subject):
        assert secret not in result.output


@pytest.mark.parametrize(
    "extra",
    [
        ["--web"],
        ["--with-token"],
        ["--account"],
        ["--with-token", "--account"],
        ["--hostname=GitCode.COM"],
        ["--hostname=ssh.gitcode.com"],
        [f"--hostname=https://{PRIVATE}@gitcode.com"],
        ["-hgitcode.com", "--hostname=gitcode.com"],
        [f"--broker-origin=https://{PRIVATE}.invalid"],
        [f"--expected-login={PRIVATE}"],
        [f"--broker-ca-sha256={PRIVATE}"],
        [f"--broker-ca-pem-base64={PRIVATE}"],
    ],
)
def test_ambiguous_or_conflicting_cli_arguments_stop_before_preflight(no_pat, monkeypatch, extra):
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    result = run("auth", "login", "--web", *flags(), *extra)
    assert result.exit_code == 2
    assert_clean(result)


@pytest.mark.parametrize("name", ["broker-origin", "expected-login", "broker-ca-sha256", "broker-ca-pem-base64"])
@pytest.mark.parametrize("missing", [None, ""])
def test_web_requires_every_explicit_nonempty_parameter(no_pat, monkeypatch, name, missing):
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    result = run("auth", "login", "--web", *flags(**{name: missing}))
    assert result.exit_code == 2 and "requires exactly one" in result.output
    assert_clean(result)


@pytest.mark.parametrize("name", ["broker-origin", "expected-login", "broker-ca-sha256", "broker-ca-pem-base64"])
def test_oauth_options_never_turn_pat_into_oauth(no_pat, monkeypatch, name):
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    result = run("auth", "login", f"--{name}={PRIVATE}", "--with-token", input=FIXTURE_TOKEN)
    assert result.exit_code == 2 and "require explicit --web" in result.output
    assert_clean(result)


@pytest.mark.parametrize(
    ("root", "env"),
    [
        (["--token", PRIVATE], {}),
        (["--token="], {}),
        (["--token", PRIVATE, "--token="], {}),
        ([], {"GC_TOKEN": PRIVATE}),
        ([], {"GC_TOKEN": ""}),
        ([], {"GC_GH_PROXY_ACTIVE": "1"}),
    ],
)
def test_explicit_token_or_proxy_denial_before_network(no_pat, win, monkeypatch, root, env):
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    result = run("auth", "login", "--web", *flags(), root=root, env=env)
    assert result.exit_code == 2 and ("cannot be combined" in result.output or "gh proxy" in result.output)
    assert_clean(result)


def test_unsupported_platform_stops_before_preflight_or_native_access(no_pat, monkeypatch):
    monkeypatch.setattr(auth, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", forbidden)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    result = run("auth", "login", "--web", *flags())
    assert result.exit_code == 1 and "requires Windows Credential Manager" in result.output
    assert_clean(result)


@pytest.mark.parametrize("value", [PRIVATE + "=", "Zh==", "Zm8=\n", "YWJj_", "éééé", r"\\untrusted\path"])
def test_web_strict_base64_never_touches_any_path(no_pat, win, monkeypatch, value):
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", forbidden)
    result = run("auth", "login", "--web", *flags(**{"broker-ca-pem-base64": value}))
    assert result.exit_code == 1 and "canonical base64" in result.output
    assert_clean(result)
    assert value not in result.output


@pytest.mark.parametrize("extra", [1, 2, 3, 16384])
def test_oversize_pem_is_rejected_before_base64_decode(no_pat, win, monkeypatch, extra):
    encoded = base64.b64encode(b"x" * (oauth_broker_client._MAX_CA_PEM + extra)).decode("ascii")
    monkeypatch.setattr(auth.base64, "b64decode", forbidden)
    monkeypatch.setattr(oauth_web_inputs, "prepare_oauth_web_inputs", forbidden)
    result = run("auth", "login", "--web", *flags(**{"broker-ca-pem-base64": encoded}))
    assert result.exit_code == 1 and "bounded" in result.output
    assert_clean(result)


@pytest.mark.parametrize(
    "change",
    [
        {"broker-origin": f"https://{PRIVATE}@broker.invalid"},
        {"expected-login": PRIVATE + "/"},
        {"broker-ca-sha256": PRIVATE},
        {"broker-ca-sha256": "0" * 64},
    ],
)
def test_trust_gate_rejects_wrong_pins_or_contract_before_native_access(no_pat, win, monkeypatch, change):
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", forbidden)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    result = run("auth", "login", "--web", *flags(**change))
    assert result.exit_code == 1
    assert_clean(result)


class MemoryVault:
    def __init__(self, events, name):
        self.events = events
        self.name = name
        self.records = {}
        self.fail_after_put = False
        self.fail_read = False

    def put(self, target, value):
        self.events.append(self.name + ".put")
        self.records[target] = value
        if self.fail_after_put:
            raise OSError(PRIVATE)

    def get(self, target):
        self.events.append(self.name + ".get")
        if self.fail_read:
            raise OSError(PRIVATE)
        return self.records[target]

    def delete(self, target):
        forbidden(target)


@pytest.fixture
def composed(no_pat, win, monkeypatch, trusted_context):
    state = SimpleNamespace(events=[], browser=[], tty=[], subject=WHO, receipt=WHO, cancel=False)
    namespace = PureWindowsPath("C:/fixture/.config/gc")
    monkeypatch.setattr(auth.config, "CONFIG_DIR", namespace)
    state.oauth = MemoryVault(state.events, "oauth")
    state.metadata = MemoryVault(state.events, "selector")
    store = oauth_credential_store.OAuthCredentialStore(state.oauth)
    selector = OAuthAccountSelectionStore(namespace, state.metadata)

    def selector_system(root):
        assert root == namespace
        state.events.append("selector.system")
        return selector

    def verify(token):
        assert token == FIXTURE_TOKEN
        state.events.append("identity")
        return state.subject

    async def acquire(origin, present, *, trust):
        assert origin == ORIGIN and type(trust) is oauth_broker_client.BrokerTrust
        assert trust.origin == ORIGIN and trust.ca_pem == CA.decode("ascii")
        state.events.append("broker")
        await present(origin + "/cli/v1/browser", PAIR)
        if state.cancel:
            raise asyncio.CancelledError(PRIVATE)
        return oauth_broker_client.BrokerReceipt(
            FIXTURE_TOKEN, state.receipt.subject, state.receipt.login, time.time() + 60
        )

    terminal = oauth_login._TerminalSession(lambda: None, state.tty.append)
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", selector_system)
    monkeypatch.setattr(oauth_credential_store, "verify_oauth_identity", verify)
    monkeypatch.setattr(oauth_login, "acquire_receipt", acquire)
    monkeypatch.setattr(
        oauth_login,
        "login_with_browser",
        partial(
            oauth_login.login_with_browser,
            _open_terminal=lambda: nullcontext(terminal),
            _opener=state.browser.append,
            _store_factory=lambda: store,
        ),
    )
    return state


def test_explicit_browser_login_only_selects_after_verified_credential_readback(composed, sandbox):
    config_path = sandbox / "config.json"
    original = b'{"token":"saved-pat-fixture"}'
    config_path.write_bytes(original)
    result = run("auth", "login", "--web", "-hgitcode.com", *flags())
    assert result.exit_code == 0 and "account selection confirmed" in result.output
    assert_clean(result)
    assert composed.events == [
        "selector.system",
        "broker",
        "identity",
        "oauth.put",
        "oauth.get",
        "selector.put",
        "selector.get",
    ]
    assert composed.browser == [ORIGIN + "/cli/v1/browser"]
    assert composed.tty == [PAIR]
    assert config_path.read_bytes() == original
    assert json.loads(next(iter(composed.metadata.records.values()))) == {
        "v": 1,
        "subject": WHO.subject,
        "login": WHO.login,
    }


@pytest.mark.parametrize("outcome", ["wrong-claim", "wrong-user", "wrong-subject", "cancel", "credential-uncertain"])
def test_unconfirmed_login_never_saves_account_selection(composed, outcome):
    stopped = ["selector.system", "broker"]
    if outcome == "wrong-claim":
        composed.receipt = OAuthIdentity(WHO.subject, WHO.login.lower())
    elif outcome == "wrong-user":
        composed.subject = OAuthIdentity(WHO.subject, WHO.login.lower())
        stopped += ["identity"]
    elif outcome == "wrong-subject":
        composed.subject = OAuthIdentity("another-subject", WHO.login)
        stopped += ["identity"]
    elif outcome == "cancel":
        composed.cancel = True
    else:
        composed.oauth.fail_read = True
        stopped += ["identity", "oauth.put", "oauth.get"]
    result = run("auth", "login", "--web", *flags())
    assert result.exit_code == 1 and "not confirmed" in result.output and "before retrying" in result.output
    assert_clean(result)
    assert composed.events == stopped and not composed.metadata.records
    assert bool(composed.oauth.records) == (outcome == "credential-uncertain")


@pytest.mark.parametrize("failure", ["put", "get"])
def test_selector_uncertain_never_retries_or_rolls_back_saved_vault(composed, failure):
    composed.metadata.fail_after_put = failure == "put"
    composed.metadata.fail_read = failure == "get"
    result = run("auth", "login", "--web", *flags())
    assert result.exit_code == 1 and "credential was saved, but account selection was not confirmed" in result.output
    assert "before retrying" in result.output
    assert_clean(result)
    wanted = ["selector.system", "broker", "identity", "oauth.put", "oauth.get", "selector.put"]
    if failure == "get":
        wanted.append("selector.get")
    assert composed.events == wanted
    assert len(composed.oauth.records) == len(composed.metadata.records) == 1


def test_real_terminal_gate_precedes_broker_and_vault(no_pat, win, trusted_context, monkeypatch):
    gate = Mock(return_value=False)
    monkeypatch.setattr(oauth_login, "_terminal_fd", gate)
    monkeypatch.setattr(oauth_login, "acquire_receipt", forbidden)
    store = Mock()
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", lambda _: store)
    result = run("auth", "login", "--web", *flags())
    assert result.exit_code == 1 and "foreground terminal" in result.output
    assert_clean(result)
    gate.assert_called_once_with(0)
    assert not store.mock_calls


def test_selector_initialization_failure_precedes_login(no_pat, win, trusted_context, monkeypatch):
    def broken(_):
        raise OSError(PRIVATE)

    monkeypatch.setattr(OAuthAccountSelectionStore, "system", broken)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    result = run("auth", "login", "--web", *flags())
    assert result.exit_code == 1 and "Cannot initialize" in result.output
    assert_clean(result)


def test_help_retains_pat_and_documents_explicit_oauth(monkeypatch):
    monkeypatch.setattr(cli, "get_token", forbidden)
    result = run("auth", "login", "--help")
    assert result.exit_code == 0 and "does not change PAT use for other commands" in result.output
    assert all(x in result.output for x in ["--with-token", "--account", "--web", "--broker-ca-pem-base64"])


def test_pat_login_status_token_and_override_unchanged_without_eager_lookup(monkeypatch):
    monkeypatch.setattr(cli, "get_token", forbidden)
    monkeypatch.setattr(OAuthAccountSelectionStore, "system", forbidden)
    monkeypatch.setattr(oauth_login, "login_with_browser", forbidden)
    pat = "fixture-pat"
    legacy = run("auth", "login", "-hGitCode.COM", "--with-token", input=pat + "\n")
    assert legacy.exit_code == 0 and "Authentication saved." in legacy.output
    assert run("auth", "token").output.strip() == pat
    assert "Logged in" in run("auth", "status").output
    assert run("auth", "token", root=["--token", "root-pat"]).output.strip() == "root-pat"
    assert run("auth", "token", env={"GC_TOKEN": "env-pat"}).output.strip() == "env-pat"
    monkeypatch.setattr(auth, "_verified_login", Mock(return_value="fixture-account"))
    named = run("auth", "login", "--with-token", "--account", input=pat + "\n", env={"GC_TOKEN": "overrides"})
    assert named.exit_code == 0 and "GC_TOKEN still overrides" in named.output
    assert run("auth", "token", "--user", "fixture-account").output.strip() == pat


@pytest.mark.parametrize(
    ("root", "env", "want"),
    [
        (["--token", "root-pat"], {"GC_TOKEN": "env-pat"}, "root-pat"),
        ([], {"GC_TOKEN": "env-pat"}, "env-pat"),
        ([], {}, "saved-pat"),
    ],
)
def test_non_auth_root_context_still_uses_ordinary_pat_precedence(sandbox, root, env, want):
    (sandbox / "config.json").write_text('{"token":"saved-pat"}', encoding="utf-8")
    obj = {}
    result = run("version", root=[*root, "--repo", "owner/repo"], env=env, obj=obj)
    assert result.exit_code == 0
    assert (obj["app"].token, obj["app"].repo) == (want, "owner/repo")


def test_non_auth_root_handling_when_pat_resolution_fails(monkeypatch):
    monkeypatch.setattr(cli, "get_token", Mock(side_effect=AuthError("no PAT")))
    obj = {}
    result = run("version", obj=obj)
    assert result.exit_code == 0 and obj["app"].token == ""
