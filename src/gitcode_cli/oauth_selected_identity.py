"""Internal, read-only verification of an explicitly scoped OAuth selection.

A selector is an untrusted hint for choosing the protected account record. It
is not authentication, a token, or permission to opt into another auth source.
"""

from __future__ import annotations

from pathlib import PureWindowsPath

from .auth_source import OAuthAccountSource
from .errors import AuthError, ConfigError
from .oauth_account_selection import OAuthAccountSelection, OAuthAccountSelectionStore
from .oauth_identity import OAuthIdentity


def _read_selection(config_root: PureWindowsPath) -> OAuthAccountSelection | None:
    unavailable = False
    try:
        value = OAuthAccountSelectionStore.system(config_root).read()
        if value is None or type(value) is OAuthAccountSelection:
            return value
    except ConfigError:
        pass
    except Exception:
        unavailable = True
    # Raise outside the handlers; a local backend failure may contain protected material.
    if unavailable:
        raise AuthError("GitCode OAuth account selection is unavailable; no fallback was used.")
    raise ConfigError("Invalid GitCode OAuth account selection or configuration root.")


def verify_selected_oauth_identity(config_root: PureWindowsPath) -> OAuthIdentity | None:
    """Re-verify the exact selected subject and login, or return None on native absence only.

    The caller supplies the scope; this path does not look it up or use any
    other credential source. The verification is for the selection read once
    at invocation; selection and credential records are not a transaction.
    """
    selected = _read_selection(config_root)
    if selected is None:
        return None
    requested = OAuthIdentity(selected.subject, selected.login)
    try:
        verified = OAuthAccountSource(requested).verified_identity()
        if type(verified) is OAuthIdentity and verified == requested:
            return verified
    except Exception:
        # Never expose backend/transport diagnostic text or exception chains.
        pass
    raise AuthError("Selected GitCode OAuth identity could not be verified; no fallback was used.")
