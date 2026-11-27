"""Synthetic storage fixtures only: no OS vault, credential, subprocess or live network."""

from __future__ import annotations

import ctypes
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


class WinAPI:
    """In-process ABI double; use real ctypes buffers but never open a vault."""

    def __init__(self):
        self.error = 0
        self.rows = {}
        self.writes = self.frees = 0
        self.read_row = None
        self.read_blob = None
        self.allocated = []
        self.CredWriteW = Mock(side_effect=self._write)
        self.CredReadW = Mock(side_effect=self._read)
        self.CredFree = Mock(side_effect=self._free)
        self.CredDeleteW = Mock(side_effect=self._delete)

    def _write(self, ptr, flags):
        row = ctypes.cast(ptr, ctypes.POINTER(module._WindowsCredential)).contents
        assert (row.flags, row.type, row.persist, flags, row.attribute_count) == (0, 1, 2, 0, 0)
        assert row.attributes is None and row.username is None and row.comment is None and row.target_alias is None
        assert row.size <= 2560 and row.size % 2 == 0 and row.blob
        self.rows[row.target] = ctypes.string_at(row.blob, row.size)
        self.writes += 1
        return 1

    def _read(self, target, kind, flags, out):
        assert (kind, flags) == (1, 0)
        if target not in self.rows:
            self.error = 1168
            return 0
        payload = self.rows[target] if self.read_blob is None else self.read_blob
        buf = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        row = module._WindowsCredential(target=target, type=1, size=len(payload), blob=ctypes.addressof(buf), persist=2)
        for name, val in (self.read_row or {}).items():
            setattr(row, name, val)
        self.allocated.append((row, buf))
        ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(module._WindowsCredential)))[0] = ctypes.pointer(row)
        return 1

    def _free(self, out):
        row, buf = self.allocated[-1]
        assert ctypes.addressof(out.contents) == ctypes.addressof(row)
        if row.blob and 0 < row.size <= 2560:
            assert not any(buf)  # even a malformed/decode-error bounded blob
        self.frees += 1

    def _delete(self, target, kind, flags):
        assert (kind, flags) == (1, 0)
        if target not in self.rows:
            self.error = 1168
            return 0
        del self.rows[target]
        return 1


@pytest.fixture
def native_windows(monkeypatch):
    native = WinAPI()
    verified(monkeypatch)
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: NOW))
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    loader = Mock(return_value=native)
    monkeypatch.setattr(module.ctypes, "WinDLL", loader, raising=False)
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: native.error, raising=False)
    store = module.OAuthCredentialStore.system()
    loader.assert_called_once_with("advapi32.dll", use_last_error=True, winmode=0x800)
    return store, native


def test_windows_credential_layout_matches_wincred_abi():
    bits64 = ctypes.sizeof(ctypes.c_void_p) == 8
    row = module._WindowsCredential
    assert ctypes.sizeof(module._FileTime) == 8
    assert ctypes.sizeof(row) == (80 if bits64 else 52)
    assert row.last_written.offset == (24 if bits64 else 16)
    assert row.size.offset == (32 if bits64 else 24)
    assert row.blob.offset == (40 if bits64 else 28)
    assert row.username.offset == (72 if bits64 else 48)


def test_native_windows_lifecycle_abi_local_scope_and_no_roaming(native_windows):
    store, native = native_windows
    assert native.CredWriteW.argtypes == [ctypes.POINTER(module._WindowsCredential), ctypes.c_uint32]
    assert native.CredReadW.argtypes == [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.POINTER(module._WindowsCredential)),
    ]
    assert native.CredDeleteW.argtypes == [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    assert [getattr(native, f).restype for f in ("CredWriteW", "CredReadW", "CredDeleteW")] == [ctypes.c_int32] * 3
    assert native.CredFree.argtypes == [ctypes.c_void_p] and native.CredFree.restype is None
    who = save(store)
    target, raw = next(iter(native.rows.items()))
    assert json.loads(raw.decode("utf-16-le"))[-1] == TOKEN
    assert not raw.endswith(b"\0\0")
    assert store.read(who).access_token == TOKEN
    store.forget(who)
    assert (native.writes, native.frees, native.rows) == (1, 3, {})
    native.CredDeleteW.assert_called_once_with(target, 1, 0)
    with pytest.raises(AuthError):
        store.read(who)
    with pytest.raises(AuthError):
        save(store, token="x" * 1281)
    assert native.writes == 1 and not native.rows and native.frees == 3


@pytest.mark.parametrize(
    "fields,payload",
    [
        ({"target": "other"}, None),
        ({"type": 2}, None),
        ({"persist": 3}, None),
        ({"blob": None}, None),
        ({"size": 0}, None),
        ({}, b"\xef"),
        ({}, b"\x00\xd8"),  # invalid standalone high surrogate
        ({}, b"x" * 2561),
    ],
)
def test_native_read_always_frees_but_never_reads_invalid_blob(native_windows, fields, payload):
    store, native = native_windows
    who = save(store)
    native.read_row, native.read_blob = fields, payload
    with pytest.raises(AuthError):
        store.read(who)
    assert native.frees == 2  # save readback and rejected read each free once


def test_null_result_is_rejected_without_free(native_windows):
    store, native = native_windows
    who = save(store)
    native.CredReadW.side_effect = None
    native.CredReadW.return_value = 1
    with pytest.raises(AuthError):
        store.read(who)
    assert native.frees == 1


def test_input_buffer_cleared_even_when_native_write_fails(native_windows, monkeypatch):
    store, native = native_windows
    native.CredWriteW.side_effect = None
    native.CredWriteW.return_value = 0
    wipe = ctypes.memset
    seen = []

    def observe(buf, value, size):
        assert TOKEN.encode("utf-16-le") in ctypes.string_at(buf, size)
        wipe(buf, value, size)
        seen.append((value, not any(ctypes.string_at(buf, size))))

    monkeypatch.setattr(module.ctypes, "memset", observe)
    with pytest.raises(AuthError):
        save(store)
    assert seen == [(0, True)] and not native.rows and native.frees == 0


@pytest.mark.parametrize("code", [1168, 1312])
def test_native_absence_is_distinct_from_an_inaccessible_vault(native_windows, code):
    store, native = native_windows
    native.CredReadW.side_effect = native.CredDeleteW.side_effect = None
    native.CredReadW.return_value = native.CredDeleteW.return_value = 0
    native.error = code
    for action in (store._backend.get, store._backend.delete):
        with pytest.raises(AuthError) as raised:
            action("fixed.synthetic.target")
        assert (type(raised.value) is module._MissingCredentialError) is (code == 1168)
