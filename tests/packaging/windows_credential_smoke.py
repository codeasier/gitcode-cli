"""Opt-in synthetic Windows Credential Manager smoke; never touches real accounts."""

from __future__ import annotations

import json
import sys
import time
from contextlib import suppress
from pathlib import PureWindowsPath
from unittest.mock import patch
from uuid import uuid4

from gitcode_cli.oauth_account_selection import OAuthAccountSelectionStore
from gitcode_cli.oauth_account_selection import _target as _selection_target
from gitcode_cli.oauth_credential_store import (
    OAuthCredentialStore,
    _MissingCredentialError,
    _target,
    _WindowsBackend,
)
from gitcode_cli.oauth_identity import OAuthIdentity


def _assert_absent(backend: _WindowsBackend, target: str) -> None:
    try:
        backend.get(target)
    except _MissingCredentialError:
        return
    raise RuntimeError("Expected the random synthetic credential slot to be absent.")


def _exercise() -> None:
    a = OAuthIdentity(f"synthetic-gc-smoke-{uuid4().hex}", "SmokeFixture")
    b = OAuthIdentity(f"synthetic-gc-control-{uuid4().hex}", a.login)
    token = "inert.smoke-fixture-token"
    expiry = int(time.time()) + 120
    writer = OAuthCredentialStore.system()
    backend = writer._backend
    if not isinstance(backend, _WindowsBackend):
        raise RuntimeError("Expected the Windows Credential Manager backend.")
    target = _target(a)
    _assert_absent(backend, target)  # refuse to touch a pre-existing slot
    _assert_absent(backend, _target(b))
    try:
        # Deterministic local identity only. No network or ambient PAT/broker.
        with patch("gitcode_cli.oauth_credential_store.verify_oauth_identity", return_value=a):
            local = writer.save(subject=a.subject, login=a.login, access_token=token, expires_at=expiry)
        reader = OAuthCredentialStore.system()
        observed = reader.read(local)
        if local != a or observed.access_token != token or observed.expires_at != expiry:
            raise RuntimeError("Synthetic verified record did not round-trip.")
        _assert_absent(backend, _target(b))
        reader.forget(a)
        _assert_absent(backend, target)
    finally:
        # Clean only our slot, even if Windows persisted before readback failed.
        with suppress(_MissingCredentialError):
            backend.delete(target)
        _assert_absent(backend, target)


def _exercise_selection() -> None:
    fixture = uuid4().hex
    account = OAuthIdentity(f"synthetic-gc-selection-{fixture}", "SmokeFixture")
    root = PureWindowsPath("C:/gitcode-cli-ci-" + fixture)
    control = PureWindowsPath("C:/gitcode-cli-control-" + fixture)
    writer = OAuthAccountSelectionStore.system(root)
    backend = writer._backend
    if not isinstance(backend, _WindowsBackend):
        raise RuntimeError("Expected the Windows Credential Manager selection backend.")
    target = _selection_target(root)
    _assert_absent(backend, target)
    _assert_absent(backend, _selection_target(control))
    _assert_absent(backend, _target(account))
    try:
        saved = writer.save_verified(account)
        reader = OAuthAccountSelectionStore.system(root)
        if reader.read() != saved or saved.subject != account.subject or saved.login != account.login:
            raise RuntimeError("Synthetic account selection did not round-trip.")
        if json.loads(backend.get(target)) != {"v": 1, "subject": account.subject, "login": account.login}:
            raise RuntimeError("The selection contains more than identity metadata.")
        if OAuthAccountSelectionStore.system(control).read() is not None:
            raise RuntimeError("Synthetic selection crossed configuration boundaries.")
        _assert_absent(backend, _target(account))
    finally:
        with suppress(_MissingCredentialError):
            backend.delete(target)
        _assert_absent(backend, target)
        _assert_absent(backend, _selection_target(control))
        _assert_absent(backend, _target(account))


def main() -> int:
    if sys.platform != "win32":
        print("Windows Credential Manager smoke requires a Windows runner.", file=sys.stderr)
        return 2
    try:
        _exercise()
        _exercise_selection()
    except Exception:
        print("Synthetic Windows Credential Manager smoke did not complete.", file=sys.stderr)
        return 1
    print("Synthetic Windows Credential Manager credential and selection round-trips and cleanup passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
