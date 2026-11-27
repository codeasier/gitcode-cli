"""Opt-in native OAuth storage. No PAT integration, plaintext fallback or refresh.

The production factory currently supports the Windows per-user Credential Manager
directly without third-party backends. Missing, invalid or expired credentials
are errors, never signals to try a PAT. Call the factory before starting an
interactive flow. Local deletion is not server-side revocation.
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Protocol, TypeVar

from .config import valid_login
from .errors import AuthError
from .oauth_identity import OAuthIdentity, verify_oauth_identity

_HOST = "gitcode.com"
_FORMAT = "pygitcode/oauth/v1"
_MAX_CHARS = 16_384
# Win32 ABI and an explicit, per-load System32-only DLL search.
_MAX_WIN_BYTES = 5 * 512
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
_ERROR_NOT_FOUND = 1168
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


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _WindowsCredential(ctypes.Structure):
    # CREDENTIALW from wincred.h. Use fixed 32-bit DWORDs/BOOL, pointer-sized
    # addresses and native alignment; use FILETIME only as data, never convert it.
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("target", ctypes.c_wchar_p),
        ("comment", ctypes.c_wchar_p),
        ("last_written", _FileTime),
        ("size", ctypes.c_uint32),
        ("blob", ctypes.c_void_p),
        ("persist", ctypes.c_uint32),
        ("attribute_count", ctypes.c_uint32),
        ("attributes", ctypes.c_void_p),
        ("target_alias", ctypes.c_wchar_p),
        ("username", ctypes.c_wchar_p),
    ]


class _MissingCredentialError(AuthError):
    """The native API explicitly reports this exact target is absent."""


def _native_windows() -> ctypes.WinDLL:
    # Trust the Windows loader and the running Python installation. Do not
    # consult PATH, repo settings, a third-party module or backend discovery.
    # This does not isolate credentials from arbitrary code in the process or
    # other processes running under the same local user.
    dll = ctypes.WinDLL("advapi32.dll", use_last_error=True, winmode=_LOAD_LIBRARY_SEARCH_SYSTEM32)
    credential = ctypes.POINTER(_WindowsCredential)
    dll.CredWriteW.argtypes = [credential, ctypes.c_uint32]
    dll.CredWriteW.restype = ctypes.c_int32
    dll.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(credential)]
    dll.CredReadW.restype = ctypes.c_int32
    dll.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    dll.CredDeleteW.restype = ctypes.c_int32
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    return dll


class _WindowsBackend:
    """Only current OS user's local-machine generic credentials (never roaming)."""

    def __init__(self, native: ctypes.WinDLL) -> None:
        self._native = native

    def put(self, target: str, secret: str) -> None:
        raw = bytearray(secret, "utf-16-le")
        buf = (ctypes.c_ubyte * len(raw)).from_buffer(raw)
        try:
            # Never truncate/split. Pass an explicit byte length, no terminator.
            if not 0 < len(raw) <= _MAX_WIN_BYTES:
                raise _invalid()
            row = _WindowsCredential(
                type=_CRED_TYPE_GENERIC,
                target=target,
                size=len(raw),
                blob=ctypes.addressof(buf),
                persist=_CRED_PERSIST_LOCAL_MACHINE,
            )
            if not self._native.CredWriteW(ctypes.byref(row), 0):
                raise _invalid()
        finally:
            ctypes.memset(buf, 0, len(raw))

    def get(self, target: str) -> str:
        out = ctypes.POINTER(_WindowsCredential)()
        if not self._native.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(out)):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                raise _MissingCredentialError("GitCode OAuth credential is absent.")
            raise _invalid()
        if not out:
            raise _invalid()
        try:
            row = out.contents
            blob, size = row.blob, row.size
            if not blob or not 0 < size <= _MAX_WIN_BYTES:
                raise _invalid()
            try:
                if (
                    row.target != target
                    or row.type != _CRED_TYPE_GENERIC
                    or row.persist != _CRED_PERSIST_LOCAL_MACHINE
                    or size % 2
                ):
                    raise _invalid()
                raw = bytearray(size)
                buf = (ctypes.c_ubyte * size).from_buffer(raw)
                try:
                    ctypes.memmove(buf, blob, size)
                    return raw.decode("utf-16-le")
                finally:
                    ctypes.memset(buf, 0, size)
            finally:
                ctypes.memset(blob, 0, size)
        finally:
            # CredReadW gives one system-allocated block. Even bad metadata/decode
            # cannot skip its release. Only wipe a non-null, bounded blob.
            self._native.CredFree(out)

    def delete(self, target: str) -> None:
        if not self._native.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                raise _MissingCredentialError("GitCode OAuth credential is absent.")
            raise _invalid()


@dataclass(frozen=True, repr=False, eq=False)
class StoredOAuthCredential:
    """Sensitive in-memory value for the future fixed-origin Bearer transport only."""

    access_token: str
    expires_at: float


class _PreparedCredential:
    """Verified, same-store, one-shot material for a local commit only."""

    def __init__(self, owner: OAuthCredentialStore, who: OAuthIdentity, expires_at: float, access_token: str) -> None:
        self._owner = owner
        self._lock = Lock()
        self._value: tuple[OAuthIdentity, float, str] | None = (who, expires_at, access_token)

    def _take(self, owner: OAuthCredentialStore) -> tuple[OAuthIdentity, float, str]:
        with self._lock:
            if owner is not self._owner or self._value is None:
                raise _invalid()
            value, self._value = self._value, None
            return value


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
        return self._commit(
            self._prepare(subject=subject, login=login, expires_at=expires_at, access_token=access_token)
        )

    def _prepare(self, *, subject: str, login: str, expires_at: float, access_token: str) -> _PreparedCredential:
        # This phase is read-only: cancellation may abandon a running identity
        # check in a worker, and that worker can never write the native vault.
        who = _identity(subject, login)
        _check_token(access_token, who)
        _check_expiry(expires_at)
        verified = _protected(lambda: verify_oauth_identity(access_token))
        if type(verified) is not OAuthIdentity or verified != who:
            raise _invalid()
        return _PreparedCredential(self, who, expires_at, access_token)

    def _commit(self, prepared: _PreparedCredential) -> OAuthIdentity:
        # Once the native write begins, the outcome may be uncertain until
        # readback. Consume the preparation before any native access.
        if type(prepared) is not _PreparedCredential:
            raise _invalid()
        who, expires_at, access_token = prepared._take(self)
        target = _target(who)
        secret = json.dumps([_FORMAT, _HOST, who.subject, who.login, expires_at, access_token], separators=(",", ":"))
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
