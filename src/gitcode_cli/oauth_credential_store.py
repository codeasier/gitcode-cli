"""Opt-in native OAuth storage. No PAT integration, plaintext fallback or refresh.

The production factory currently supports the Windows per-user Credential Manager
via optional pywin32 only. A missing backend, missing credential or invalid/expired
record is an error, never a signal to try a PAT. Call the factory before starting
an interactive flow. Local deletion is not server-side revocation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.machinery import ExtensionFileLoader
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from sysconfig import get_path
from types import ModuleType
from typing import Protocol, TypeVar

from .config import valid_login
from .errors import AuthError
from .oauth_identity import OAuthIdentity, verify_oauth_identity

_HOST = "gitcode.com"
_FORMAT = "pygitcode/oauth/v1"
_MAX_CHARS = 16_384
_MAX_WIN_BYTES = 5 * 512
_Result = TypeVar("_Result")


def _invalid() -> AuthError:
    return AuthError("Invalid, expired or mismatched GitCode OAuth credential.")


def _protected(operation: Callable[[], _Result]) -> _Result:
    # Native/transport exceptions may contain the secret, including via __context__.
    # Raise outside the handler: neither stderr nor exception chains expose it.
    try:
        return operation()
    except Exception:
        pass
    raise AuthError("GitCode OAuth credential operation unavailable; no fallback was used.")


def _identity(subject: str, login: str) -> OAuthIdentity:
    if (
        type(subject) is not str
        or not 0 < len(subject) <= 512
        or not subject.isprintable()
        or any(c.isspace() for c in subject)
        or type(login) is not str
        or not valid_login(login)
    ):
        raise _invalid()
    return OAuthIdentity(subject, login)


def _target(identity: OAuthIdentity) -> str:
    if type(identity) is not OAuthIdentity:
        raise _invalid()
    _identity(identity.subject, identity.login)
    # Windows target names are case-insensitive; GitCode's subject is opaque and
    # case-sensitive. Never key by mutable login, nor expose identity as a path.
    digest = hashlib.sha256(identity.subject.encode("utf-8")).hexdigest()
    return f"{_FORMAT}/{_HOST}/{digest}"


def _check_token(access_token: str, identity: OAuthIdentity) -> None:
    if (
        type(access_token) is not str
        or not 0 < len(access_token) <= 8192
        or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", access_token)
        or access_token in identity.login
        or access_token in identity.subject
    ):
        raise _invalid()


def _check_expiry(expires_at: float) -> None:
    if type(expires_at) not in (int, float) or not time.time() < expires_at <= 2**53:
        raise _invalid()


class _SecretBackend(Protocol):
    def put(self, target: str, secret: str) -> None: ...
    def get(self, target: str) -> str: ...
    def delete(self, target: str) -> None: ...


def _native_windows() -> ModuleType:
    # Load only the release pywin32 extension installed in THIS interpreter.
    # A similarly named plugin/module on PATH, sys.path or in the current repo
    # must not be allowed to receive a credential.
    prefix = Path(get_path("platlib")).resolve(strict=True)
    binary = prefix / "win32" / "win32cred.pyd"
    if binary.resolve(strict=True) != binary:
        raise _invalid()
    loader = ExtensionFileLoader("win32cred", str(binary))
    spec = spec_from_file_location("win32cred", binary, loader=loader)
    if spec is None:
        raise _invalid()
    native = module_from_spec(spec)
    loader.exec_module(native)
    return native


class _WindowsBackend:
    """Only current OS user's local-machine generic credentials (never roaming)."""

    def __init__(self, native: ModuleType) -> None:
        self._native = native

    def put(self, target: str, secret: str) -> None:
        # Pywin32 CredWrite accepts Unicode and measures the UTF-16LE byte count;
        # CredRead returns bytes. Never truncate or split an oversized credential.
        if len(secret.encode("utf-16-le")) > _MAX_WIN_BYTES:
            raise _invalid()
        self._native.CredWrite(
            {
                "TargetName": target,
                "Type": self._native.CRED_TYPE_GENERIC,
                "Persist": self._native.CRED_PERSIST_LOCAL_MACHINE,
                "CredentialBlob": secret,
            },
            0,
        )

    def get(self, target: str) -> str:
        row = self._native.CredRead(target, self._native.CRED_TYPE_GENERIC, 0)
        if (
            type(row) is not dict
            or row.get("TargetName") != target
            or row.get("Type") != self._native.CRED_TYPE_GENERIC
            or row.get("Persist") != self._native.CRED_PERSIST_LOCAL_MACHINE
        ):
            raise _invalid()
        blob = row.get("CredentialBlob")
        if type(blob) is not bytes or not 0 < len(blob) <= _MAX_WIN_BYTES:
            raise _invalid()
        return blob.decode("utf-16-le")

    def delete(self, target: str) -> None:
        self._native.CredDelete(target, self._native.CRED_TYPE_GENERIC, 0)


@dataclass(frozen=True, repr=False, eq=False)
class StoredOAuthCredential:
    """Sensitive in-memory value for the future fixed-origin Bearer transport only."""

    access_token: str
    expires_at: float


class OAuthCredentialStore:
    """Internal OAuth-only store; do not pass its credentials into legacy PAT routes."""

    def __init__(self, backend: _SecretBackend) -> None:
        self._backend = backend

    @classmethod
    def system(cls) -> OAuthCredentialStore:
        if sys.platform != "win32":
            raise AuthError("No supported OS-protected GitCode OAuth credential backend on this platform.")
        # Never discover plugins, invoke an OS utility with a secret, or select
        # a backend from configuration/environment.
        return cls(_WindowsBackend(_protected(_native_windows)))

    def save(self, *, subject: str, login: str, expires_at: float, access_token: str) -> OAuthIdentity:
        """Verify the broker's claimed owner with GitCode before any local write."""
        who = _identity(subject, login)
        _check_token(access_token, who)
        _check_expiry(expires_at)
        verified = _protected(lambda: verify_oauth_identity(access_token))
        if type(verified) is not OAuthIdentity or verified != who:
            raise _invalid()
        target = _target(who)
        secret = json.dumps([_FORMAT, _HOST, subject, login, expires_at, access_token], separators=(",", ":"))
        _check_expiry(expires_at)  # verification can take time
        _protected(lambda: self._backend.put(target, secret))
        # A lost/uncertain write or a concurrent replacement is not login success.
        # Do not retry, overwrite or delete a possibly valid newer credential.
        saved = self.read(who)
        if not hmac.compare_digest(saved.access_token, access_token) or saved.expires_at != expires_at:
            raise _invalid()
        return who

    def _record(self, who: OAuthIdentity) -> StoredOAuthCredential:
        target = _target(who)
        raw = _protected(lambda: self._backend.get(target))
        if type(raw) is not str or len(raw) > _MAX_CHARS:
            raise _invalid()
        # A fixed-length sequence has no duplicate keys or optional fields.
        fields = _protected(lambda: json.loads(raw))
        if type(fields) is not list or len(fields) != 6 or fields[:4] != [_FORMAT, _HOST, who.subject, who.login]:
            raise _invalid()
        expires_at, access_token = fields[4:]
        _check_token(access_token, who)
        if type(expires_at) not in (int, float) or not 0 < expires_at <= 2**53:
            raise _invalid()
        return StoredOAuthCredential(access_token, expires_at)

    def read(self, who: OAuthIdentity) -> StoredOAuthCredential:
        """Read only the exact selected identity; never return an expired token."""
        credential = self._record(who)
        _check_expiry(credential.expires_at)
        return credential

    def forget(self, who: OAuthIdentity) -> None:
        """Forget this account locally, including an expired record. Never revoke remotely."""
        self._record(who)
        target = _target(who)
        _protected(lambda: self._backend.delete(target))
