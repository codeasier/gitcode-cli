"""Synthetic storage fixtures only: no OS vault, credential, subprocess or live network."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import respx

from gitcode_cli import oauth_credential_store as module
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_identity import OAuthIdentity

WHO = OAuthIdentity("00ExactSub", "Case.User")
TOKEN = "inert.fixture-token"
NOW = 1000
EXP = NOW + 60
URL = "https://api.gitcode.com/api/v5/user"


class Memory:
    def __init__(self):
        self.rows = {}
        self.writes = 0

    def put(self, target, secret):
        self.rows[target] = secret
        self.writes += 1

    def get(self, target):
        return self.rows[target]

    def delete(self, target):
        del self.rows[target]


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: NOW))
    backend = Memory()
    return module.OAuthCredentialStore(backend), backend


def save(store, who=WHO, token=TOKEN, expires=EXP):
    return store.save(subject=who.subject, login=who.login, access_token=token, expires_at=expires)


def verified(monkeypatch, who=WHO):
    monkeypatch.setattr(module, "verify_oauth_identity", lambda _: who)


def test_real_identity_verifier_exact_request_then_save_read_forget(storage, tmp_path, monkeypatch):
    store, backend = storage
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GC_TOKEN", "wrong.ambient")
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")

    def serve(request):
        assert str(request.url) == URL and request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url) and "private-token" not in request.headers
        assert backend.writes == 0
        return httpx.Response(200, json={"login": WHO.login, "id": WHO.subject})

    with respx.mock(assert_all_mocked=True) as routes:
        routes.get(URL).mock(side_effect=serve)
        assert save(store) == WHO
        saved = store.read(WHO)
        assert saved.access_token == TOKEN and saved.expires_at == EXP
        assert TOKEN not in repr(saved) and TOKEN not in str(saved)
        assert list(backend.rows)[0].startswith("pygitcode/oauth/v1/gitcode.com/")
        assert all(s not in list(backend.rows)[0] for s in [WHO.login, WHO.subject, TOKEN])
        store.forget(WHO)
        assert not backend.rows and backend.writes == 1 and len(routes.calls) == 1
        with pytest.raises(AuthError):
            store.read(WHO)
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("field,value", [("subject", "00EXACTSUB"), ("login", "case.user")])
def test_verified_identity_mismatch_never_writes_or_deletes(storage, monkeypatch, field, value):
    store, backend = storage
    verified(monkeypatch)
    save(store)
    before = backend.rows.copy()
    other = OAuthIdentity(**{**vars(WHO), field: value})
    with pytest.raises(AuthError):
        save(store, other)
    for op in (store.read, store.forget):
        with pytest.raises(AuthError):
            op(other)
    assert backend.rows == before and backend.writes == 1


def test_reused_login_and_case_sensitive_subject_are_separate(storage, monkeypatch):
    store, backend = storage
    other = OAuthIdentity(WHO.subject.upper(), WHO.login)
    for who, token in [(WHO, TOKEN), (other, "second.inert-token")]:
        verified(monkeypatch, who)
        save(store, who, token)
    assert len({k.lower() for k in backend.rows}) == 2
    store.forget(other)
    assert store.read(WHO).access_token == TOKEN


@pytest.mark.parametrize(
    "subject,login,token,expires",
    [
        ("", WHO.login, TOKEN, EXP),
        ("with space", WHO.login, TOKEN, EXP),
        (WHO.subject, "../other", TOKEN, EXP),
        (WHO.subject, WHO.login, "header\nvalue", EXP),
        (TOKEN, WHO.login, TOKEN, EXP),
        (WHO.subject, TOKEN, TOKEN, EXP),
        (WHO.subject, WHO.login, TOKEN, True),
        (WHO.subject, WHO.login, TOKEN, EXP + 2**53),
        (WHO.subject, WHO.login, TOKEN, float("inf")),
        (WHO.subject, WHO.login, TOKEN, float("nan")),
        (WHO.subject, WHO.login, TOKEN, NOW),
    ],
)
def test_bad_input_fails_before_io(storage, monkeypatch, subject, login, token, expires):
    store, backend = storage
    checker = Mock()
    monkeypatch.setattr(module, "verify_oauth_identity", checker)
    with pytest.raises(AuthError):
        store.save(subject=subject, login=login, access_token=token, expires_at=expires)
    checker.assert_not_called()
    assert backend.writes == 0


def test_expiry_rechecked_after_verification_and_on_read_without_deleting(storage, monkeypatch):
    store, backend = storage
    verified(monkeypatch)
    save(store)
    before = backend.rows.copy()
    monkeypatch.setattr(module.time, "time", lambda: EXP)
    with pytest.raises(AuthError):
        store.read(WHO)
    assert backend.rows == before
    store.forget(WHO)
    assert not backend.rows
    clock = iter((NOW, EXP))
    monkeypatch.setattr(module.time, "time", lambda: next(clock))
    with pytest.raises(AuthError):
        save(store)
    assert not backend.rows and backend.writes == 1


@pytest.mark.parametrize(
    "payload",
    [
        0,
        "{bad",
        "x" * 16_385,
        json.dumps({}),
        json.dumps(["v1"]),
        json.dumps(["pygitcode/oauth/v2", "gitcode.com", WHO.subject, WHO.login, EXP, TOKEN]),
        json.dumps(["pygitcode/oauth/v1", "gitcode.evil", WHO.subject, WHO.login, EXP, TOKEN]),
        json.dumps(["pygitcode/oauth/v1", "gitcode.com", WHO.subject, WHO.login, False, TOKEN]),
        json.dumps(["pygitcode/oauth/v1", "gitcode.com", WHO.subject, WHO.login, EXP, "bad\x00token"]),
    ],
)
def test_corrupt_or_foreign_record_cannot_be_returned_or_erased(storage, monkeypatch, payload):
    store, backend = storage
    verified(monkeypatch)
    save(store)
    key = next(iter(backend.rows))
    backend.rows[key] = payload
    for op in (store.read, store.forget):
        with pytest.raises(AuthError):
            op(WHO)
    assert backend.rows[key] == payload


@pytest.mark.parametrize("failure", ["verify", "put", "get", "delete"])
def test_native_or_verifier_errors_never_leak_or_retry(storage, monkeypatch, capsys, caplog, failure):
    store, backend = storage
    verified(monkeypatch)
    save(store)
    failing = Mock(side_effect=RuntimeError("credential: " + TOKEN))
    if failure == "verify":
        monkeypatch.setattr(module, "verify_oauth_identity", failing)
    else:
        monkeypatch.setattr(backend, failure, failing)
    op = {
        "verify": lambda: save(store),
        "put": lambda: save(store),
        "get": lambda: store.read(WHO),
        "delete": lambda: store.forget(WHO),
    }[failure]
    with pytest.raises(AuthError) as raised:
        op()
    assert failing.call_count == 1 and TOKEN not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert TOKEN not in caplog.text and capsys.readouterr() == ("", "")


def test_system_ignores_ambient_selection_and_fails_closed_when_unsupported(monkeypatch):
    native_import = Mock(side_effect=ImportError(TOKEN))
    monkeypatch.setattr(module, "_native_windows", native_import)
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")
    for platform in ("darwin", "linux", "win32"):
        monkeypatch.setattr(module, "sys", SimpleNamespace(platform=platform))
        with pytest.raises(AuthError) as raised:
            module.OAuthCredentialStore.system()
        assert TOKEN not in str(raised.value)
    native_import.assert_called_once_with()


def test_native_windows_shape_utf16_limit_and_no_roaming(monkeypatch):
    # Model pywin32's documented CredWrite Unicode -> CredRead UTF-16LE bytes.
    verified(monkeypatch)
    native = Mock(CRED_TYPE_GENERIC=1, CRED_PERSIST_LOCAL_MACHINE=2)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module, "_native_windows", lambda: native)
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: NOW))
    store = module.OAuthCredentialStore.system()

    def put(record, flags):
        native.CredRead.return_value = {**record, "CredentialBlob": record["CredentialBlob"].encode("utf-16-le")}

    native.CredWrite.side_effect = put
    who = save(store)
    (record, flags), _ = native.CredWrite.call_args
    assert flags == 0 and set(record) == {"CredentialBlob", "TargetName", "Type", "Persist"}
    assert record["Type"] == 1 and record["Persist"] == 2
    target, blob = record["TargetName"], record["CredentialBlob"].encode("utf-16-le")
    native.CredRead.return_value = {**record, "CredentialBlob": blob}
    assert store.read(who).access_token == TOKEN
    store.forget(who)
    native.CredRead.assert_called_with(target, 1, 0)
    native.CredDelete.assert_called_once_with(target, 1, 0)
    with pytest.raises(AuthError):
        save(store, token="x" * 1281)
    assert native.CredWrite.call_count == 1  # no truncation or multi-slot write
    for mutation in [
        {"TargetName": "other"},
        {"Type": 2},
        {"Persist": 3},
        {"CredentialBlob": "text"},
        {"CredentialBlob": b"\xef"},
        {"CredentialBlob": b"x" * 2561},
    ]:
        native.CredRead.return_value = {**record, "CredentialBlob": blob, **mutation}
        with pytest.raises(AuthError):
            store.read(who)


def test_loader_ignores_uninstalled_python_module(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "get_path", lambda _: str(tmp_path / "installed"))
    (tmp_path / "installed" / "win32").mkdir(parents=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    with pytest.raises(AuthError):
        module.OAuthCredentialStore.system()


def test_uncertain_or_substituted_write_is_not_login_success(storage, monkeypatch):
    store, backend = storage
    verified(monkeypatch)
    put = backend.put

    def substitute(target, raw):
        put(target, raw.replace(TOKEN, "other.inert"))

    monkeypatch.setattr(backend, "put", substitute)
    with pytest.raises(AuthError):
        save(store)
    assert backend.writes == 1 and next(iter(backend.rows.values())).endswith('"other.inert"]')


def test_wrong_identity_type_fails_before_backend_access(storage):
    store, backend = storage
    for op in (store.read, store.forget):
        with pytest.raises(AuthError):
            op(None)
    assert not backend.rows


def test_loader_selects_fixed_installed_extension_only(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    fixed = installed / "win32" / "win32cred.pyd"
    fixed.parent.mkdir(parents=True)
    fixed.touch()  # inert placeholder; no native code loads
    monkeypatch.setattr(module, "get_path", lambda name: str(installed) if name == "platlib" else None)
    native = SimpleNamespace()
    built = Mock(return_value=native)
    executed = Mock()
    monkeypatch.setattr(module, "module_from_spec", built)
    monkeypatch.setattr(module.ExtensionFileLoader, "exec_module", executed)
    assert module._native_windows() is native
    spec = built.call_args.args[0]
    assert spec.name == "win32cred" and spec.origin == str(fixed)
    assert type(spec.loader) is module.ExtensionFileLoader
    executed.assert_called_once_with(native)
