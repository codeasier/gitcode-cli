"""Explicit local preflight for a future CLI OAuth entry point, not command wiring.

The portable gate takes explicit immutable bytes and verifies the full digest
before parsing them. It does not discover inputs in the environment, cwd, repo,
legacy PAT configuration, broker or public trust store. No file, network, browser
or credential access occurs in that gate. A future caller owns the boundary that
provides the operator's verified local input bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

from .config import valid_login
from .errors import AuthError
from .oauth_broker_client import _MAX_CA_PEM, BrokerTrust, _broker_context, _origin

_SHA256 = re.compile(r"[a-fA-F0-9]{64}")


@dataclass(frozen=True, repr=False)
class OAuthWebInputs:
    """Exact expected account spelling and one origin-bound in-memory CA, not credentials."""

    expected_login: str
    broker_trust: BrokerTrust


def _explicit_inputs(expected_login: str, broker_origin: str, ca_sha256: str) -> tuple[str, str]:
    if type(expected_login) is not str or not valid_login(expected_login):
        raise AuthError("Expected an explicit valid GitCode OAuth login.")
    if type(ca_sha256) is not str or len(ca_sha256) != 64 or _SHA256.fullmatch(ca_sha256) is None:
        raise AuthError("Expected a full SHA-256 fingerprint for the OAuth broker CA PEM.")
    try:
        return _origin(broker_origin), ca_sha256.lower()
    except AuthError:
        pass
    raise AuthError("Expected an independently trusted canonical HTTPS broker origin.")


def prepare_oauth_web_inputs(
    *, expected_login: str, broker_origin: str, ca_pem: bytes, ca_sha256: str
) -> OAuthWebInputs:
    """Pure input gate: exact login, canonical HTTPS origin and a pinned immutable CA PEM.

    ca_sha256 is 64 hex digits for the original PEM bytes, not the DER encoding;
    uppercase hex is accepted, separators, whitespace and auto-computed pins are
    not. The exact proved bytes are used without newline normalization.
    """
    origin, fingerprint = _explicit_inputs(expected_login, broker_origin, ca_sha256)
    return _prepare(expected_login, origin, ca_pem, fingerprint)


def _prepare(expected_login: str, origin: str, raw: bytes, fingerprint: str) -> OAuthWebInputs:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_CA_PEM:
        raise AuthError("Expected one bounded immutable OAuth broker CA PEM.")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), fingerprint):
        raise AuthError("OAuth broker CA PEM does not match the supplied SHA-256 fingerprint.")
    try:
        trust = BrokerTrust(origin, raw.decode("ascii"))
        _broker_context(origin, trust)
    except (AuthError, OSError, ValueError):
        # Unicode and SSL failures may retain input; do not chain them.
        pass
    else:
        return OAuthWebInputs(expected_login, trust)
    raise AuthError("Expected one valid CA certificate in the explicit OAuth broker CA PEM.")
