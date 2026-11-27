"""Internal identity check for a freshly obtained GitCode OAuth access token.

This does not obtain, persist, or route the credential to any ordinary CLI command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._redact import redact
from .config import valid_login
from .errors import AuthError
from .repo_read import bounded_json_response


@dataclass(frozen=True)
class OAuthIdentity:
    subject: str
    login: str


def verify_oauth_identity(access_token: str) -> OAuthIdentity:
    """Read the authenticated subject and login; never derive either from the other."""
    if (
        not isinstance(access_token, str)
        or not 0 < len(access_token) <= 8192
        or not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", access_token)
    ):
        raise AuthError("Invalid GitCode OAuth access token.")
    profile, _, _ = bounded_json_response("OAuth identity", "/user", {}, access_token, (), strict_json=True)
    if isinstance(profile, dict) and "error" not in profile:
        subject, login = profile.get("id"), profile.get("login")
        # GitCode documents id as a string (including 24-character hexadecimal
        # examples), not a numeric ID. Preserve its exact spelling.
        if (
            isinstance(subject, str)
            and 0 < len(subject) <= 512
            and subject.isprintable()
            and not any(c.isspace() for c in subject)
            and isinstance(login, str)
            and valid_login(login)
            and all(redact(value, access_token) == value for value in (subject, login))
        ):
            return OAuthIdentity(subject, login)
    raise AuthError("GitCode did not return a verified OAuth identity.")
