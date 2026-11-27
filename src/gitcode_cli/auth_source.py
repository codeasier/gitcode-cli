"""Internal source selection; no command currently opts into OAuth.

The selector is explicit on purpose: a missing account in OAuth mode is an
error, not another spelling of PAT mode. Never route the OAuth capability to
AppContext, GitCodeClient, token display, arbitrary URLs or legacy services.
"""

from __future__ import annotations

import time
from typing import Literal, overload

from .config import get_token
from .errors import AuthError
from .oauth_credential_store import OAuthCredentialStore
from .oauth_identity import OAuthIdentity, verify_oauth_identity


class LegacyPATSource:
    """Preserve existing PAT precedence, including the no-token error."""

    __slots__ = ("_explicit_pat",)

    def __init__(self, explicit_pat: str | None) -> None:
        if explicit_pat is not None and type(explicit_pat) is not str:
            raise AuthError("Invalid GitCode PAT selection.")
        self._explicit_pat = explicit_pat

    def legacy_token(self) -> str:
        return get_token(self._explicit_pat)


class OAuthAccountSource:
    """Holds only the selected identity, never the credential or a generic client."""

    __slots__ = ("_account",)

    def __init__(self, account: OAuthIdentity) -> None:
        if type(account) is not OAuthIdentity:
            raise AuthError("Select an exact GitCode OAuth account.")
        self._account = account

    def verified_identity(self) -> OAuthIdentity:
        """Re-read the vault for this use and match BOTH authoritative fields."""
        account = self._account
        try:
            credential = OAuthCredentialStore.system().read(account)
            # The store already checks expiry on read. The fixed check may itself
            # take time; do not report an authenticated account beyond expiry.
            verified = verify_oauth_identity(credential.access_token)
            if type(verified) is OAuthIdentity and verified == account and time.time() < credential.expires_at:
                return verified
        except Exception:
            # A backend/transport error may contain the credential or response.
            # Raise outside the handler, without retaining its exception chain.
            pass
        raise AuthError("Selected GitCode OAuth identity could not be verified; no fallback was used.")


@overload
def select_auth_source(
    mode: Literal["pat"], *, account: None = None, explicit_pat: str | None = None
) -> LegacyPATSource: ...


@overload
def select_auth_source(
    mode: Literal["oauth"], *, account: OAuthIdentity, explicit_pat: None = None
) -> OAuthAccountSource: ...


def select_auth_source(
    mode: Literal["pat", "oauth"], *, account: OAuthIdentity | None = None, explicit_pat: str | None = None
) -> LegacyPATSource | OAuthAccountSource:
    """Select without reading any config, environment, OS vault or network."""
    if type(mode) is str:
        if mode == "pat" and account is None:
            return LegacyPATSource(explicit_pat)
        if mode == "oauth" and account is not None and explicit_pat is None:
            return OAuthAccountSource(account)
    raise AuthError("Invalid or conflicting GitCode credential source selection.")
