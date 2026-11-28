"""Read-only selection-to-identity contract; no real vault, App or network."""

from __future__ import annotations

import json
from pathlib import PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock, call

import httpx
import pytest
import respx

from gitcode_cli import auth_source, config, oauth_account_selection, oauth_credential_store, oauth_selected_identity
from gitcode_cli.errors import AuthError, ConfigError
from gitcode_cli.oauth_identity import OAuthIdentity

ROOT = PureWindowsPath("C:/fixture/selected")
OTHER = PureWindowsPath("C:/fixture/other")
URL = "https://api.gitcode.com/api/v5/user"
WHO = OAuthIdentity("00ABC0123", "Mixed.Login")
TOKEN = "disposable.synthetic-oauth"
PAT = "unrelated.synthetic-pat"
NOW = 1000
EXP = NOW + 90


@pytest.fixture
def stores(monkeypatch):
    # Exercise actual selection framing and credential checks. Only stand in
    # for the OS backend/factory, never a real user or credential.
    selected_target = oauth_account_selection._target(ROOT)
    credential_target = oauth_credential_store._target(WHO)
    rows = {
        selected_target: json.dumps({"v": 1, "subject": WHO.subject, "login": WHO.login}),
        credential_target: json.dumps(["pygitcode/oauth/v1", "gitcode.com", WHO.subject, WHO.login, EXP, TOKEN]),
    }

    def get(target):
        if target not in rows:
            raise oauth_credential_store._MissingCredentialError(TOKEN)
        result = rows[target]
        if isinstance(result, Exception):
            raise result
        return result

    backend = Mock(spec=["get", "put", "delete"])
    backend.get.side_effect = get
    backend.put.side_effect = AssertionError("read-only helper wrote vault")
    backend.delete.side_effect = AssertionError("read-only helper deleted from vault")
    selector = Mock(side_effect=lambda root: oauth_account_selection.OAuthAccountSelectionStore(root, backend))
    record = Mock(return_value=oauth_credential_store.OAuthCredentialStore(backend))
    pat = Mock(side_effect=AssertionError("read-only OAuth helper looked up a PAT"))
    monkeypatch.setenv("GC_TOKEN", PAT)
    monkeypatch.setattr(auth_source, "get_token", pat)
    monkeypatch.setattr(config, "get_token", pat)
    monkeypatch.setattr(oauth_account_selection.OAuthAccountSelectionStore, "system", selector)
    monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", record)
    clock = SimpleNamespace(time=lambda: NOW)
    monkeypatch.setattr(oauth_credential_store, "time", clock)
    monkeypatch.setattr(auth_source, "time", clock)
    yield SimpleNamespace(
        rows=rows,
        selector=selector,
        record=record,
        backend=backend,
        selected_target=selected_target,
        credential_target=credential_target,
    )
    backend.put.assert_not_called()
    backend.delete.assert_not_called()
    pat.assert_not_called()


def assert_sanitized(error):
    assert TOKEN not in str(error) and PAT not in str(error)
    assert error.__cause__ is None and error.__context__ is None


def test_exact_scope_and_both_identity_fields_reverified_before_return(stores):
    def serve(request):
        assert request.method == "GET" and str(request.url) == URL and not request.content
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert {"cookie", "private-token", "proxy-authorization"}.isdisjoint(request.headers)
        assert [key for key, value in request.headers.items() if TOKEN in value] == ["authorization"]
        return httpx.Response(200, json={"id": WHO.subject, "login": WHO.login, "ignored": TOKEN})

    with respx.mock(assert_all_mocked=True) as routes:
        routes.get(URL).mock(side_effect=serve)
        result = oauth_selected_identity.verify_selected_oauth_identity(ROOT)
        assert type(result) is OAuthIdentity and result == WHO
        assert vars(result) == {"subject": WHO.subject, "login": WHO.login}
        assert TOKEN not in repr(result)
        assert len(routes.calls) == 1
    stores.selector.assert_called_once_with(ROOT)
    stores.record.assert_called_once_with()
    assert stores.backend.mock_calls == [call.get(stores.selected_target), call.get(stores.credential_target)]


def test_exact_absent_scope_is_none_without_borrowing_another_root_or_vault(stores):
    with respx.mock(assert_all_mocked=True) as routes:
        assert oauth_selected_identity.verify_selected_oauth_identity(OTHER) is None
        assert not routes.calls
    stores.selector.assert_called_once_with(OTHER)
    stores.record.assert_not_called()
    stores.backend.get.assert_called_once_with(oauth_account_selection._target(OTHER))


@pytest.mark.parametrize(
    ("corrupt", "kind"),
    [
        (b"x", ConfigError),
        ("[]", ConfigError),
        ('{"v":1,"subject":"x","login":"y","token":"ignored"}', ConfigError),
        ('{"v":1,"subject":"x","login":"y","login":"z"}', ConfigError),
        ('{"v":1,"subject":"x","login":".."}', ConfigError),
        (" " * 1281, ConfigError),
        (None, ConfigError),
        (OSError(TOKEN), AuthError),
        (KeyError(TOKEN), AuthError),
        (AuthError(TOKEN), AuthError),
        (ConfigError(TOKEN), AuthError),
    ],
)
def test_corrupt_or_unavailable_selection_is_not_absence(stores, corrupt, kind):
    stores.rows[stores.selected_target] = corrupt
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(kind) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    assert not routes.calls
    stores.record.assert_not_called()
    stores.backend.get.assert_called_once_with(stores.selected_target)
    assert_sanitized(raised.value)


@pytest.mark.parametrize(
    "root", [None, "C:/fixture", PureWindowsPath("C:fixture"), PureWindowsPath("C:/parent/../root")]
)
def test_invalid_or_untyped_root_has_no_account_fallback(stores, root):
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(ConfigError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(root)
    stores.selector.assert_called_once_with(root)
    stores.record.assert_not_called()
    stores.backend.get.assert_not_called()
    assert not routes.calls
    assert_sanitized(raised.value)


def test_unsupported_platform_uses_real_selector_gate(monkeypatch):
    # No mocked factory here. Only choose the platform and prove the system
    # factory fails before loading anything native or considering another source.
    native = Mock(side_effect=AssertionError("would load native vault"))
    credentials = Mock(side_effect=AssertionError("would load credential store"))
    legacy = Mock(side_effect=AssertionError("would select PAT"))
    monkeypatch.setattr(oauth_account_selection.sys, "platform", "linux")
    monkeypatch.setattr(oauth_account_selection, "_native_windows", native)
    monkeypatch.setattr(auth_source.OAuthCredentialStore, "system", credentials)
    monkeypatch.setattr(auth_source, "get_token", legacy)
    with (
        respx.mock(assert_all_mocked=True) as routes,
        pytest.raises(AuthError, match="selection is unavailable") as raised,
    ):
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    native.assert_not_called()
    credentials.assert_not_called()
    legacy.assert_not_called()
    assert not routes.calls
    assert_sanitized(raised.value)


@pytest.mark.parametrize("failure", ["missing", "expired", "subject", "login", "malformed", "permission"])
def test_unapproved_credential_never_reaches_verifier(stores, failure):
    credential_target = stores.credential_target
    if failure == "missing":
        stores.rows.pop(credential_target)
    elif failure == "permission":
        stores.rows[credential_target] = OSError(TOKEN)
    else:
        row = json.loads(stores.rows[credential_target])
        if failure == "expired":
            row[4] = NOW
        elif failure == "subject":
            row[2] = WHO.subject.lower()
        elif failure == "login":
            row[3] = WHO.login.lower()
        else:
            row.append(TOKEN)
        stores.rows[credential_target] = json.dumps(row)
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(AuthError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    assert not routes.calls
    assert stores.backend.mock_calls == [call.get(stores.selected_target), call.get(credential_target)]
    assert_sanitized(raised.value)


@pytest.mark.parametrize(
    ("status", "profile"),
    [
        (200, {"id": WHO.subject.lower(), "login": WHO.login}),
        (200, {"id": WHO.subject, "login": WHO.login.lower()}),
        (200, {"id": WHO.subject}),
        (200, {"id": WHO.subject, "login": TOKEN}),
        (403, {"error": TOKEN}),
        (302, {"id": WHO.subject, "login": WHO.login}),
    ],
)
def test_verification_is_exact_and_fresh_without_pat_or_redirect(stores, status, profile):
    with respx.mock(assert_all_mocked=True) as routes:
        route = routes.get(URL)
        route.respond(200, json={"id": WHO.subject, "login": WHO.login})
        assert oauth_selected_identity.verify_selected_oauth_identity(ROOT) == WHO
        route.respond(status, json=profile, headers={"Location": f"https://unrelated.invalid/{TOKEN}"})
        with pytest.raises(AuthError) as raised:
            oauth_selected_identity.verify_selected_oauth_identity(ROOT)
        assert len(routes.calls) == 2
    assert stores.backend.mock_calls == [call.get(stores.selected_target), call.get(stores.credential_target)] * 2
    assert_sanitized(raised.value)


def test_unexpected_verifier_exception_is_sanitized_and_never_retried(stores, monkeypatch):
    verifier = Mock(side_effect=RuntimeError(TOKEN))
    monkeypatch.setattr(auth_source, "verify_oauth_identity", verifier)
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(AuthError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    assert not routes.calls
    assert stores.backend.mock_calls == [call.get(stores.selected_target), call.get(stores.credential_target)]
    verifier.assert_called_once_with(TOKEN)
    assert_sanitized(raised.value)


@pytest.mark.parametrize("unexpected", [{"subject": WHO.subject, "login": WHO.login}, WHO, False])
def test_selector_type_cannot_flag_a_value_as_an_authenticated_identity(stores, unexpected):
    stores.selector.side_effect = None
    stores.selector.return_value = SimpleNamespace(read=lambda: unexpected)
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(ConfigError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    stores.record.assert_not_called()
    stores.backend.get.assert_not_called()
    assert not routes.calls
    assert_sanitized(raised.value)


def test_factory_rejection_does_not_preserve_exception_text_or_chain(stores):
    stores.selector.side_effect = ConfigError(TOKEN)
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(ConfigError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    stores.selector.assert_called_once_with(ROOT)
    stores.record.assert_not_called()
    stores.backend.get.assert_not_called()
    assert not routes.calls
    assert_sanitized(raised.value)


@pytest.mark.parametrize(
    "unconfirmed",
    [
        oauth_account_selection.OAuthAccountSelection(WHO.subject, WHO.login),
        OAuthIdentity("other", WHO.login),
        OAuthIdentity(WHO.subject, "other"),
    ],
)
def test_source_result_must_confirm_exact_identity_type_and_fields(stores, monkeypatch, unconfirmed):
    source = Mock(return_value=SimpleNamespace(verified_identity=lambda: unconfirmed))
    monkeypatch.setattr(oauth_selected_identity, "OAuthAccountSource", source)
    with respx.mock(assert_all_mocked=True) as routes, pytest.raises(AuthError) as raised:
        oauth_selected_identity.verify_selected_oauth_identity(ROOT)
    source.assert_called_once_with(WHO)
    assert_sanitized(raised.value)
    assert not routes.calls
