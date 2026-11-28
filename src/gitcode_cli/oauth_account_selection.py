"""Local OAuth account selection metadata. This module does not authenticate anyone.

Only save the identity returned by a successful verified credential write. A read
returns a *selector*, never proof of identity, a credential or permission to use
a PAT. A consumer must verify the selected account against the protected account
record separately. There is no command wiring, token lookup or automatic fallback.

Windows stores one complete descriptor in a separate current-user WinCred record.
An explicit local configuration root scopes its name; the exact lexical path is
hashed and is never opened, resolved or followed. Different spellings can select
different records. There is no plaintext file or filesystem fallback. This is
not isolation from the same OS user, a CAS, or a transaction with the credential
write. A lost write reply/readback requires reconciliation, not an automatic retry.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import PureWindowsPath

from .config import valid_login
from .errors import AuthError, ConfigError
from .oauth_credential_store import (
    _MissingCredentialError,
    _native_windows,
    _protected,
    _SecretBackend,
    _WindowsBackend,
)
from .oauth_identity import OAuthIdentity

_PREFIX = "pygitcode/oauth-selection/v1/gitcode.com/"
_MAX_UTF16_BYTES = 2560  # One complete WinCred generic record; never split or truncate.


@dataclass(frozen=True)
class OAuthAccountSelection:
    """Untrusted non-secret metadata; intentionally not an OAuthIdentity."""

    subject: str
    login: str


def _invalid() -> ConfigError:
    return ConfigError("Invalid GitCode OAuth account selection.")


def _selection(subject: object, login: object) -> OAuthAccountSelection:
    if (
        type(subject) is not str
        or not 0 < len(subject) <= 512
        or not subject.isprintable()
        or any(c.isspace() for c in subject)
        or type(login) is not str
        or not valid_login(login)
    ):
        raise _invalid()
    return OAuthAccountSelection(subject, login)


def _encode(identity: OAuthIdentity) -> str:
    if type(identity) is not OAuthIdentity:
        raise _invalid()
    row = _selection(identity.subject, identity.login)
    raw = json.dumps({"v": 1, "subject": row.subject, "login": row.login}, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-16-le")) > _MAX_UTF16_BYTES:
        raise _invalid()
    return raw


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def _decode(raw: object) -> OAuthAccountSelection:
    # Bound work before copying, parsing or converting the contents of a native record.
    if type(raw) is str and 0 < len(raw) <= _MAX_UTF16_BYTES // 2:
        try:
            if len(raw.encode("utf-16-le")) <= _MAX_UTF16_BYTES:
                obj = json.loads(raw, object_pairs_hook=_unique)
                if (
                    type(obj) is dict
                    and obj.keys() == {"v", "subject", "login"}
                    and type(obj["v"]) is int
                    and obj["v"] == 1
                ):
                    return _selection(obj["subject"], obj["login"])
        except (ValueError, RecursionError):
            # Raise outside the handler: JSONDecodeError.doc may carry the entire record.
            pass
    raise _invalid()


def _target(root: PureWindowsPath) -> str:
    # Local, fully qualified, explicit namespace only. No host lookup, environment
    # discovery, cwd, directory access or profile path in the OS target name.
    if not isinstance(root, PureWindowsPath) or re.fullmatch(r"[A-Za-z]:", root.drive) is None:
        raise _invalid()
    if not root.is_absolute() or len(root.parts) < 2 or ".." in root.parts:
        raise _invalid()
    name = root.as_posix()
    if not name.isprintable() or len(name) > 32767:
        raise _invalid()
    return _PREFIX + hashlib.sha256(name.encode("utf-8")).hexdigest()


class OAuthAccountSelectionStore:
    """Separate metadata store. None means native not-found for this exact target only."""

    def __init__(self, config_root: PureWindowsPath, backend: _SecretBackend) -> None:
        self._target = _target(config_root)
        self._backend = backend

    @classmethod
    def system(cls, config_root: PureWindowsPath) -> OAuthAccountSelectionStore:
        if sys.platform != "win32":
            raise AuthError("No supported OS-protected GitCode OAuth account selection on this platform.")
        # Validate before loading the OS backend. Never probe by writing a dummy record.
        _target(config_root)
        return cls(config_root, _WindowsBackend(_protected(_native_windows)))

    def read(self) -> OAuthAccountSelection | None:
        def fetch() -> tuple[bool, object]:
            try:
                return True, self._backend.get(self._target)
            except _MissingCredentialError:
                return False, None

        found, raw = _protected(fetch)  # Native access errors are not an absent selection.
        return _decode(raw) if found else None

    def save_verified(self, identity: OAuthIdentity) -> OAuthAccountSelection:
        """Persist the caller's already verified identity; the descriptor cannot verify it."""
        raw = _encode(identity)
        _protected(lambda: self._backend.put(self._target, raw))
        observed = self.read()
        if observed is None or observed.subject != identity.subject or observed.login != identity.login:
            raise AuthError("GitCode OAuth account selection write was not confirmed; reconcile before retrying.")
        return observed
