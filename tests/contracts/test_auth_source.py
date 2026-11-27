"""Synthetic offline tests; no real vault, credentials, network or command activation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import respx

from gitcode_cli import auth_source, config, oauth_credential_store
from gitcode_cli.errors import AuthError, ConfigError
from gitcode_cli.oauth_identity import OAuthIdentity

URL = "https://api.gitcode.com/api/v5/user"
ACCOUNT = OAuthIdentity("oA17", "Fixture.User")
TOKEN = "fixture.oauth-only"
PAT = "fixture.old-pat"
NOW = 1000
EXP = NOW + 90


@pytest.fixture
def vault(monkeypatch):
    # Real store framing, account/expiry validation and fixed-origin verifier;
    # replace only the OS credential backend and clock. Never use the OS vault.
    backend = Mock()
    backend.get.return_value = json.dumps(
        ["pygitcode/oauth/v1", "gitcode.com", ACCOUNT.subject, ACCOUNT.login, EXP, TOKEN]
    )
    store = oauth_credential_store.OAuthCredentialStore(backend)
    monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", staticmethod(lambda: store))
    clock = SimpleNamespace(time=lambda: NOW)
    monkeypatch.setattr(oauth_credential_store, "time", clock)
    monkeypatch.setattr(auth_source, "time", clock)
    return backend, clock


def forbid_pat(monkeypatch):
    monkeypatch.setenv("GC_TOKEN", PAT)
    legacy = Mock(side_effect=AssertionError("PAT lookup not allowed"))
    monkeypatch.setattr(auth_source, "get_token", legacy)
    return legacy


def test_pat_precedence_remains_flag_env_file_then_error(tmp_config_dir, monkeypatch):
    factory = Mock(side_effect=AssertionError("no vault in PAT mode"))
    monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", factory)
    config.save_config({"token": "fixture.saved-pat"})
    monkeypatch.setenv("GC_TOKEN", PAT)
    selected = auth_source.select_auth_source("pat", explicit_pat="fixture.flag-pat")
    assert "fixture.flag-pat" not in repr(selected) and "fixture.flag-pat" not in str(selected)
    assert selected.legacy_token() == "fixture.flag-pat"
    assert auth_source.select_auth_source("pat").legacy_token() == PAT
    assert auth_source.select_auth_source("pat", explicit_pat="").legacy_token() == PAT
    monkeypatch.delenv("GC_TOKEN")
    assert auth_source.select_auth_source("pat").legacy_token() == "fixture.saved-pat"
    config.save_config({})
    with pytest.raises(ConfigError):
        auth_source.select_auth_source("pat").legacy_token()
    factory.assert_not_called()


@pytest.mark.parametrize(
    "mode,account,pat",
    [
        ("oauth", None, None),
        ("oauth", ACCOUNT, PAT),
        ("oauth", ACCOUNT, ""),
        ("oauth", "untyped-account", None),
        ("pat", ACCOUNT, None),
        ("pat", None, ACCOUNT),
        ("OAuth", ACCOUNT, None),
        (None, None, None),
        ("", None, None),
    ],
)
def test_conflicting_unknown_or_incomplete_mode_fails_before_resolution(monkeypatch, mode, account, pat):
    legacy = forbid_pat(monkeypatch)
    factory = Mock()
    monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", factory)
    with pytest.raises(AuthError) as caught:
        auth_source.select_auth_source(mode, account=account, explicit_pat=pat)
    assert PAT not in str(caught.value)
    legacy.assert_not_called()
    factory.assert_not_called()


def test_oauth_only_fixed_bearer_identity_no_arbitrary_request_or_secret_accessor(vault, monkeypatch):
    backend, _ = vault
    legacy = forbid_pat(monkeypatch)
    selected = auth_source.select_auth_source("oauth", account=ACCOUNT)
    # No token, generic client, or transport that accepts a route. The handle
    # contains only the requested account and can be created without reading it.
    assert not isinstance(selected, str)
    assert not hasattr(selected, "__dict__")
    assert {name for name in dir(selected) if not name.startswith("_")} == {"verified_identity"}
    assert all(v not in repr(selected) + str(selected) for v in (ACCOUNT.login, ACCOUNT.subject, TOKEN))
    backend.get.assert_not_called()

    def serve(request):
        assert str(request.url) == URL and request.method == "GET" and not request.content
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert not {"cookie", "private-token", "proxy-authorization"}.intersection(request.headers)
        assert [key for key, value in request.headers.items() if TOKEN in value] == ["authorization"]
        return httpx.Response(200, json={"id": ACCOUNT.subject, "login": ACCOUNT.login, "ignored": TOKEN})

    with respx.mock(assert_all_mocked=True) as routes:
        routes.get(URL).mock(side_effect=serve)
        for _ in range(2):
            who = selected.verified_identity()
            assert who == ACCOUNT and set(vars(who)) == {"subject", "login"}
        assert len(routes.calls) == 2
    assert backend.get.call_count == 2 and backend.get.call_args_list[0] == backend.get.call_args_list[1]
    backend.put.assert_not_called()
    backend.delete.assert_not_called()
    legacy.assert_not_called()


@pytest.mark.parametrize("failure", ["unsupported", "missing", "expired", "wrong-account", "invalid-record"])
def test_invalid_storage_never_falls_back_or_contacts_any_host(vault, monkeypatch, failure):
    backend, clock = vault
    legacy = forbid_pat(monkeypatch)
    if failure == "unsupported":
        monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", Mock(side_effect=AuthError(TOKEN)))
    elif failure == "missing":
        backend.get.side_effect = KeyError(TOKEN)
    elif failure == "expired":
        clock.time = lambda: EXP
    elif failure == "invalid-record":
        backend.get.return_value = f"invalid fixture: {TOKEN}"
    who = OAuthIdentity(ACCOUNT.subject, "Other.Login") if failure == "wrong-account" else ACCOUNT
    with respx.mock() as routes, pytest.raises(AuthError) as caught:
        auth_source.select_auth_source("oauth", account=who).verified_identity()
    assert len(routes.calls) == 0
    assert caught.value.__context__ is None and caught.value.__cause__ is None and TOKEN not in str(caught.value)
    legacy.assert_not_called()


@pytest.mark.parametrize("failure", ["subject", "login", "expiry", "redirect", "rejected", "network"])
def test_no_false_identity_no_retry_or_legacy_after_verification_failure(vault, monkeypatch, failure):
    _, clock = vault
    legacy = forbid_pat(monkeypatch)

    def serve(request):
        if failure == "expiry":
            clock.time = lambda: EXP
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": f"https://inert.invalid/{TOKEN}"})
        if failure == "rejected":
            return httpx.Response(401, text=TOKEN)
        if failure == "network":
            raise httpx.ConnectError(TOKEN, request=request)
        return httpx.Response(
            200,
            json={
                "id": ACCOUNT.subject.lower() if failure == "subject" else ACCOUNT.subject,
                "login": ACCOUNT.login.lower() if failure == "login" else ACCOUNT.login,
            },
        )

    with respx.mock(assert_all_mocked=True) as routes:
        routes.get(URL).mock(side_effect=serve)
        selected = auth_source.select_auth_source("oauth", account=ACCOUNT)
        with pytest.raises(AuthError) as caught:
            selected.verified_identity()
        assert len(routes.calls) == 1
    assert TOKEN not in str(caught.value) and caught.value.__context__ is None and caught.value.__cause__ is None
    legacy.assert_not_called()
