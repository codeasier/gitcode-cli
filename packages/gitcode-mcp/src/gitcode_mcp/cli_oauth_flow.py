"""Internal transactions for a separate CLI OAuth broker; no routes or transport.

The embedding broker must provide a dedicated encrypted store/key, pin its own
HTTPS origin and OAuth application at startup, and provide a trusted fixed-origin
Bearer-only /user identity verifier. Never take these dependencies from a request.
The HTTP layer must still enforce secure cookies, same-origin POST consent, safe
display of the verified identity, non-logging redirects and request rate limits.
No refresh token, MCP grant, auth code or plaintext CLI verifier is persisted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .oauth_config import https_url
from .oauth_store import OAuthStore, OAuthTransaction

_TTL = 300
_KIND = "flow"  # Counts towards the store's pending-login quota in all phases.
_PREFIX = "cli.oauth.v1:"
_NONCE = re.compile(r"[A-Za-z0-9_-]{43}")
_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*")


class FlowRejected(ValueError):
    """One opaque failure for invalid, expired, denied, misbound and replayed input."""

    def __init__(self) -> None:
        super().__init__("CLI authorization transaction unavailable.")


def _nonce() -> str:
    return secrets.token_urlsafe(32)


def _encoded(value: object) -> str:
    if type(value) is not str or not _NONCE.fullmatch(value):
        raise FlowRejected()
    return value


def _digest(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode("ascii")).digest()).decode()[:-1]


def _proof(value: object, expected: str) -> None:
    if not hmac.compare_digest(_digest(_encoded(value)), expected):
        raise FlowRejected()


def _valid_token(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 8192 and bool(_TOKEN.fullmatch(value))


@dataclass(frozen=True)
class Start:
    selector: str = field(repr=False)
    browser_start: str = field(repr=False)


@dataclass(frozen=True)
class BrowserBinding:
    cookie: str = field(repr=False)
    upstream_state: str = field(repr=False)


@dataclass(frozen=True)
class ExchangeClaim:
    proof: str = field(repr=False)


@dataclass(frozen=True)
class Subject:
    """Independent /user result; login is for display, subject is for identity."""

    subject: str = field(repr=False)
    login: str = field(repr=False)


@dataclass(frozen=True)
class Consent:
    identity: Subject
    csrf: str = field(repr=False)


@dataclass(frozen=True)
class Redeemed:
    identity: Subject
    access_token: str = field(repr=False)
    expires_at: float


class CLIFlow:
    def __init__(
        self,
        store: OAuthStore,
        *,
        broker_origin: str,
        client_id: str,
        verify_identity: Callable[[str], Awaitable[Subject]],
    ) -> None:
        if (
            type(broker_origin) is not str
            or len(broker_origin) > 1024
            or "?" in broker_origin
            or "#" in broker_origin
            or type(client_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9._~-]{1,256}", client_id)
        ):
            raise FlowRejected()
        origin = https_url(broker_origin, "CLI broker origin", origin=True)
        self._binding = [
            "cli.oauth.v1",
            "https://gitcode.com",
            client_id,
            origin + "/cli/v1/callback",
            origin,
        ]
        self._store = store
        self._verify_identity = verify_identity

    def _read(self, tx: OAuthTransaction, selector: str, phase: str) -> dict[str, Any]:
        row = tx.get(_KIND, _PREFIX + _encoded(selector))
        if not row or row.get("binding") != self._binding or row.get("phase") != phase:
            raise FlowRejected()
        return row

    def _save(self, tx: OAuthTransaction, selector: str, row: dict[str, Any], phase: str) -> None:
        row["phase"] = phase
        tx.put(_KIND, _PREFIX + selector, row, row["deadline"])

    def create(self, challenge: str) -> Start:
        """CLI supplies only S256 of its random, private 32-byte base64url verifier."""
        challenge = _encoded(challenge)
        # Base64url of 256 bits has precisely two trailing zero pad bits.
        if challenge[-1] not in "AEIMQUYcgkosw048":
            raise FlowRejected()
        start = Start(_nonce(), _nonce())
        with self._store.transaction() as tx:
            # OAuthStore.put is an upsert: never overwrite a live flow on collision.
            if tx.get(_KIND, _PREFIX + start.selector) is not None:
                raise FlowRejected()
            row = dict(
                binding=self._binding,
                deadline=time.time() + _TTL,
                challenge=challenge,
                start=_digest(start.browser_start),
            )
            self._save(tx, start.selector, row, "new")
        return start

    def begin(self, selector: str, browser_start: str) -> BrowserBinding:
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "new")
            _proof(browser_start, row.pop("start"))
            browser = BrowserBinding(_nonce(), _nonce())
            row.update(cookie=_digest(browser.cookie), state=_digest(browser.upstream_state))
            self._save(tx, selector, row, "callback")
        return browser

    def claim_callback(self, selector: str, cookie: str, state: str) -> ExchangeClaim:
        """Claim before exchanging the code. A duplicate callback must never exchange."""
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "callback")
            _proof(cookie, row["cookie"])
            _proof(state, row.pop("state"))
            claim = ExchangeClaim(_nonce())
            row["claim"] = _digest(claim.proof)
            self._save(tx, selector, row, "exchange")
        return claim

    async def complete_exchange(
        self, selector: str, claim: ExchangeClaim, access_token: str, expires_at: float
    ) -> Consent:
        """Accept an exchanged credential only after an independent identity lookup.

        The claim is server-only. Consume it before invoking the verifier outside
        the transaction; verification failure/crash cannot restart the exchange.
        """
        if (
            type(claim) is not ExchangeClaim
            or not _valid_token(access_token)
            or type(expires_at) not in (int, float)
            or not time.time() < expires_at <= 2**53
            or not math.isfinite(expires_at)
        ):
            raise FlowRejected()
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "exchange")
            _proof(claim.proof, row["claim"])
            self._save(tx, selector, row, "verifying")
        try:
            who = await self._verify_identity(access_token)
        except Exception:
            # An upstream exception might include the credential in a message or URL.
            who = None
        if type(who) is not Subject or not all(
            type(v) is str
            and 0 < len(v) <= 512
            and v.isprintable()
            and not any(c.isspace() for c in v)
            and access_token not in v
            for v in (who.subject, who.login)
        ):
            raise FlowRejected()
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "verifying")
            _proof(claim.proof, row.pop("claim"))
            if expires_at <= time.time():
                raise FlowRejected()
            csrf = _nonce()
            row.update(
                csrf=_digest(csrf),
                subject=who.subject,
                login=who.login,
                token=access_token,
                expires=expires_at,
            )
            row["deadline"] = min(row["deadline"], expires_at)
            self._save(tx, selector, row, "consent")
        return Consent(who, csrf)

    def consent_view(self, selector: str, cookie: str) -> Consent:
        """Render only the current bound subject on a clean URL. Reload supersedes old forms."""
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "consent")
            _proof(cookie, row["cookie"])
            csrf = _nonce()
            row["csrf"] = _digest(csrf)
            self._save(tx, selector, row, "consent")
            return Consent(Subject(row["subject"], row["login"]), csrf)

    def decide(self, selector: str, cookie: str, csrf: str, *, allow: bool) -> None:
        if type(allow) is not bool:
            raise FlowRejected()
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "consent")
            _proof(cookie, row.pop("cookie"))
            _proof(csrf, row.pop("csrf"))
            if allow:
                self._save(tx, selector, row, "ready")
            else:
                tx.delete(_KIND, _PREFIX + selector)

    def redeem(self, selector: str, verifier: str) -> Redeemed:
        with self._store.transaction() as tx:
            row = self._read(tx, selector, "ready")
            _proof(verifier, row["challenge"])
            result = Redeemed(Subject(row["subject"], row["login"]), row["token"], row["expires"])
            tx.delete(_KIND, _PREFIX + selector)
        return result
