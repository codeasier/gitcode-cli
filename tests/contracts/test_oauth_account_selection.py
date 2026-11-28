"""Isolated selector contract. No filesystem, secrets, native vault or network required."""

import json
from pathlib import PureWindowsPath
from unittest.mock import Mock

import pytest

from gitcode_cli import oauth_account_selection as module
from gitcode_cli import oauth_credential_store as vault
from gitcode_cli.errors import AuthError, ConfigError
from gitcode_cli.oauth_identity import OAuthIdentity

ROOT = PureWindowsPath("C:/User/Private/gc")
WHO = OAuthIdentity("0000Alpha-Ö字", "Mixed.GC_1")


class MemoryBackend:
    def __init__(self):
        self.rows = {}
        self.writes = []

    def get(self, target):
        if target not in self.rows:
            raise vault._MissingCredentialError("absent")
        return self.rows[target]

    def put(self, target, secret):
        self.writes.append(target)
        self.rows[target] = secret

    def delete(self, target):
        pytest.fail("selector must not delete a credential or roll back an uncertain write")


def test_separate_record_and_roundtrip_without_accessing_config_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("GC_TOKEN", "unused-synthetic-fixture")
    legacy = tmp_path / "config.json"
    legacy.write_bytes(b"unchanged")
    backend = MemoryBackend()
    token_target = vault._target(WHO)
    backend.rows[token_target] = "unchanged synthetic account record"
    store = module.OAuthAccountSelectionStore(ROOT, backend)
    assert store.read() is None
    selection = store.save_verified(WHO)
    assert selection == module.OAuthAccountSelection(WHO.subject, WHO.login)
    assert type(selection) is not OAuthIdentity
    (key,) = backend.writes
    assert key.startswith("pygitcode/oauth-selection/v1/gitcode.com/")
    assert len(key.rsplit("/", 1)[-1]) == 64
    assert all(s not in key for s in (WHO.subject, WHO.login, "Private", "User"))
    assert backend.rows[key] == '{"v":1,"subject":"0000Alpha-Ö字","login":"Mixed.GC_1"}'
    assert backend.rows[token_target] == "unchanged synthetic account record"
    assert module.OAuthAccountSelectionStore(ROOT, backend).read() == selection
    other = module.OAuthAccountSelectionStore(PureWindowsPath("D:/User/Private/gc"), backend)
    assert other.read() is None
    other.save_verified(OAuthIdentity("other", "b"))
    assert store.read() == selection
    assert legacy.read_bytes() == b"unchanged"
    assert list(tmp_path.iterdir()) == [legacy]


@pytest.mark.parametrize(
    "root",
    [
        "C:/root",
        PureWindowsPath("relative/gc"),
        PureWindowsPath("C:relative/gc"),
        PureWindowsPath("C:/"),
        PureWindowsPath("C:/profile/../root"),
        PureWindowsPath("//server/share/gc"),
        PureWindowsPath("//?/C:/profile/gc"),
        PureWindowsPath("D:/profile/\ud800"),
        PureWindowsPath("D:/gc" + "A" * 32768),
    ],
)
def test_reject_ambiguous_or_unsupported_namespace(root):
    with pytest.raises(ConfigError):
        module.OAuthAccountSelectionStore(root, MemoryBackend())


@pytest.mark.parametrize(
    "wire",
    [
        None,
        b"{}",
        "",
        "[]",
        '{"v":1}',
        '{"v":1,"subject":"a","login":"b","token":"fixture"}',
        '{"v":1,"subject":"a","login":"b","origin":"https://example.invalid"}',
        '{"v":1,"subject":"a","login":"b","tenant":"x"}',
        '{"v":1,"subject":"a","login":"b","pat_fallback":true}',
        '{"v":1,"subject":"a","login":"b","\\u0076":1}',
        '{"v":true,"subject":"a","login":"b"}',
        '{"v":1.0,"subject":"a","login":"b"}',
        '{"v":2,"subject":"a","login":"b"}',
        '{"v":"1","subject":"a","login":"b"}',
        '{"v":1,"subject":42,"login":"b"}',
        '{"v":1,"subject":"a b","login":"b"}',
        '{"v":1,"subject":[],"login":"b"}',
        '{"v":1,"subject":"a","login":"."}',
        '{"v":1,"subject":"a","login":"b","login":"c"}',
        '{"v":1,"subject":"a","login":"b"} junk',
        '{"v":1,"subject":"\\ud800","login":"b"}',
        "\udc00",
        "[" * 1200,
        " " * 1281,
        '{"v":1,"subject":"a","login":"secret value here"}',
    ],
)
def test_malformed_or_extra_fields_are_errors_not_absence(wire):
    backend = MemoryBackend()
    backend.rows[module._target(ROOT)] = wire
    with pytest.raises(ConfigError) as error:
        module.OAuthAccountSelectionStore(ROOT, backend).read()
    assert "secret" not in str(error.value)
    assert error.value.__context__ is None
    assert not backend.writes


@pytest.mark.parametrize(
    "identity",
    [
        None,
        {"subject": "a", "login": "b"},
        module.OAuthAccountSelection("a", "b"),
        OAuthIdentity("a" * 513, "a"),
        OAuthIdentity("", "a"),
        OAuthIdentity("a\n", "me"),
        OAuthIdentity("a", "x" * 256),
        OAuthIdentity("a", "a/b"),
        OAuthIdentity("a", ".."),
        OAuthIdentity("\U0001f300" * 512, "x" * 255),
    ],
)
def test_invalid_or_oversize_write_fails_without_touching_backend(identity):
    backend = Mock(spec=MemoryBackend)
    store = module.OAuthAccountSelectionStore(ROOT, backend)
    with pytest.raises(ConfigError):
        store.save_verified(identity)
    assert backend.mock_calls == []


def test_exact_native_blob_boundary_counts_utf16_units_not_python_characters():
    # Native generic records allow 2,560 bytes at most. These IDs all pass the
    # same verified-subject character grammar used by the separate credential store.
    subject = "\U0001f300" * 510
    prefix = len(
        json.dumps({"v": 1, "subject": subject, "login": ""}, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-16-le"
        )
    )
    n = (2560 - prefix) // 2
    assert 1 <= n < 255
    who = OAuthIdentity(subject, "x" * n)
    raw = module._encode(who)
    assert len(raw.encode("utf-16-le")) == 2560
    assert module._decode(raw).subject == subject
    with pytest.raises(ConfigError):
        module._encode(OAuthIdentity(subject, "x" * (n + 1)))
    with pytest.raises(ConfigError):
        module._decode(raw + " ")


@pytest.mark.parametrize("failure", ["access", "readback-access", "mismatch", "disappeared", "uncertain"])
def test_native_failure_is_never_absence_retry_or_rollback(failure):
    backend = Mock(spec=MemoryBackend)
    store = module.OAuthAccountSelectionStore(ROOT, backend)
    backend.get.side_effect = RuntimeError("opaque synthetic sensitive error")
    if failure == "access":
        with pytest.raises(AuthError) as error:
            store.read()
        backend.put.assert_not_called()
    else:
        if failure == "mismatch":
            backend.get.side_effect = None
            backend.get.return_value = module._encode(OAuthIdentity("other", WHO.login))
        elif failure == "disappeared":
            backend.get.side_effect = vault._MissingCredentialError("gone")
        elif failure == "uncertain":
            backend.put.side_effect = RuntimeError("opaque synthetic sensitive error")
        with pytest.raises(AuthError) as error:
            store.save_verified(WHO)
        assert backend.put.call_count == 1
    assert error.value.__context__ is None
    assert "sensitive" not in str(error.value)
    backend.delete.assert_not_called()


def test_unsupported_platform_and_bad_root_do_not_probe_or_fallback(monkeypatch):
    native = Mock(side_effect=AssertionError("no native load"))
    monkeypatch.setattr(module, "_native_windows", native)
    monkeypatch.setattr(module.sys, "platform", "linux")
    with pytest.raises(AuthError):
        module.OAuthAccountSelectionStore.system(ROOT)
    monkeypatch.setattr(module.sys, "platform", "win32")
    with pytest.raises(ConfigError):
        module.OAuthAccountSelectionStore.system(PureWindowsPath("relative"))
    native.assert_not_called()


def test_windows_factory_selects_builtin_backend_without_probing(monkeypatch):
    dll = object()
    native = Mock(return_value=dll)
    backend = MemoryBackend()
    make = Mock(return_value=backend)
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "_native_windows", native)
    monkeypatch.setattr(module, "_WindowsBackend", make)
    store = module.OAuthAccountSelectionStore.system(ROOT)
    native.assert_called_once_with()
    make.assert_called_once_with(dll)
    assert not backend.writes
    store.save_verified(WHO)
    assert store.read().login == WHO.login
