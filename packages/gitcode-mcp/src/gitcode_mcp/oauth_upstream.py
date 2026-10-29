"""Bounded GitCode OAuth requests with credentials kept out of diagnostics."""

from __future__ import annotations

import json
import logging
import math
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

AUTHORIZE_URL = "https://gitcode.com/oauth/authorize"
TOKEN_URL = "https://gitcode.com/oauth/token"
USER_URL = "https://api.gitcode.com/api/v5/user"
MAX_RESPONSE_BYTES = 65_536


class OAuthUpstreamError(Exception):
    """Only fixed, credential-free messages cross the upstream boundary."""

    _MESSAGES = {
        "invalid_configuration": "GitCode OAuth configuration is invalid.",
        "invalid_request": "GitCode OAuth request parameters are invalid.",
        "invalid_grant": "GitCode authorization has expired or was rejected; reconnect.",
        "invalid_client": "GitCode rejected the OAuth application's credentials.",
        "timeout": "GitCode OAuth did not respond in time.",
        "network_error": "The GitCode OAuth request could not be completed.",
        "upstream_redirect": "GitCode OAuth returned an unexpected redirect.",
        "upstream_error": "GitCode OAuth returned an unsuccessful response.",
        "invalid_response": "GitCode OAuth returned an invalid response.",
        "response_too_large": "GitCode OAuth returned a response exceeding the size limit.",
    }

    def __init__(self, code: str) -> None:
        # A caller cannot accidentally turn an upstream error string into a message.
        self.code = code if code in self._MESSAGES else "upstream_error"
        super().__init__(self._MESSAGES[self.code])


@dataclass(frozen=True)
class UpstreamTokens:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float
    scope: str = field(repr=False)


@dataclass(frozen=True)
class GitCodeIdentity:
    subject: str
    login: str


_credential_io: ContextVar[bool] = ContextVar("gitcode_oauth_upstream_io", default=False)


class _CredentialRequestLogFilter(logging.Filter):
    """Suppress only this client's transport logs, without changing logger levels.

    GitCode documents refresh tokens in the token endpoint's query string, and
    httpx logs complete request URLs at INFO. httpcore DEBUG can additionally
    log echoed response headers or exceptions. Context-local filtering covers
    those requests and leaves other concurrent clients' logging unchanged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not _credential_io.get()


_credential_log_filter = _CredentialRequestLogFilter()
_HTTP_LOGGERS = (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)


def _credential(value: Any, *, optional: bool = False) -> bool:
    return (
        isinstance(value, str)
        and (bool(value) or optional)
        and len(value) <= MAX_RESPONSE_BYTES
        and value.isascii()
        and all(32 < ord(character) < 127 for character in value)
    )


def _identity(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 512
        and not any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    )


def _positive_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


class GitCodeOAuthUpstream:
    """A dedicated, non-retrying client for the fixed GitCode OAuth endpoints."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        callback_url: str,
        *,
        scopes: tuple[str, ...] = (),
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not _credential(client_id)
            or not _credential(client_secret)
            or not _positive_number(timeout)
            or not isinstance(callback_url, str)
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in callback_url
            )
            or not isinstance(scopes, tuple)
            or not all(_credential(scope) for scope in scopes)
        ):
            raise OAuthUpstreamError("invalid_configuration")
        try:
            callback = urlsplit(callback_url)
            valid_callback = (
                bool(callback.hostname)
                and callback.username is None
                and callback.password is None
                and not callback.query
                and not callback.fragment
                and (
                    callback.scheme == "https"
                    or (
                        callback.scheme == "http"
                        and callback.hostname in {"127.0.0.1", "localhost", "::1"}
                    )
                )
            )
        except ValueError:
            raise OAuthUpstreamError("invalid_configuration") from None
        if not valid_callback:
            raise OAuthUpstreamError("invalid_configuration")

        self._client_id = client_id
        self._client_secret = client_secret
        self._callback_url = callback_url
        self._scopes = scopes
        # Logger.addFilter is idempotent for the same filter instance. A ContextVar
        # also keeps this safe when several OAuth clients run concurrently.
        for name in _HTTP_LOGGERS:
            logging.getLogger(name).addFilter(_credential_log_filter)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            # This pooled client serves several independent OAuth grants. A
            # response cookie must never become another user's authentication.
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "codeasier-gitcode-mcp",
            },
        )

    def authorization_url(self, state: str) -> str:
        if not _credential(state):
            raise OAuthUpstreamError("invalid_request")
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._callback_url,
            "response_type": "code",
            "state": state,
            "prompt": "consent",
        }
        if self._scopes:
            params["scope"] = " ".join(self._scopes)
        return AUTHORIZE_URL + "?" + urlencode(params)

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        context_token = _credential_io.set(True)
        try:
            async with self._client.stream(method, url, **kwargs) as response:
                if 300 <= response.status_code < 400:
                    raise OAuthUpstreamError("upstream_redirect")
                if url == USER_URL and response.status_code in {401, 403}:
                    raise OAuthUpstreamError("invalid_grant")
                content = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise OAuthUpstreamError("response_too_large")
                    content.extend(chunk)
                try:
                    payload = json.loads(content)
                except (ValueError, UnicodeError):
                    if not 200 <= response.status_code < 300:
                        raise OAuthUpstreamError("upstream_error") from None
                    raise OAuthUpstreamError("invalid_response") from None
                if not 200 <= response.status_code < 300:
                    upstream_error = payload.get("error") if isinstance(payload, dict) else None
                    if isinstance(upstream_error, str) and upstream_error in {
                        "invalid_grant",
                        "invalid_client",
                    }:
                        raise OAuthUpstreamError(upstream_error)
                    raise OAuthUpstreamError("upstream_error")
                if not isinstance(payload, dict):
                    raise OAuthUpstreamError("invalid_response")
                # Some providers return a structured OAuth error with HTTP 200.
                if "error" in payload:
                    upstream_error = payload["error"]
                    if isinstance(upstream_error, str) and upstream_error in {
                        "invalid_grant",
                        "invalid_client",
                    }:
                        raise OAuthUpstreamError(upstream_error)
                    raise OAuthUpstreamError("upstream_error")
                return payload
        except OAuthUpstreamError:
            raise
        except httpx.TimeoutException:
            raise OAuthUpstreamError("timeout") from None
        except httpx.HTTPError:
            raise OAuthUpstreamError("network_error") from None
        except (ValueError, UnicodeError):
            raise OAuthUpstreamError("invalid_response") from None
        finally:
            _credential_io.reset(context_token)

    @staticmethod
    def _tokens(payload: dict[str, Any], *, previous_refresh: str = "") -> UpstreamTokens:
        access = payload.get("access_token")
        refresh = payload.get("refresh_token", previous_refresh)
        duration = payload.get("expires_in")
        scope = payload.get("scope", "")
        if (
            not _credential(access)
            or not _credential(refresh, optional=True)
            or not _positive_number(duration)
            or not isinstance(scope, str)
            or len(scope) > 4096
            or any(ord(character) < 32 or ord(character) == 127 for character in scope)
        ):
            raise OAuthUpstreamError("invalid_response")
        expires_at = time.time() + duration
        if not math.isfinite(expires_at):
            raise OAuthUpstreamError("invalid_response")
        return UpstreamTokens(access, refresh, expires_at, scope)

    async def exchange_code(self, code: str) -> UpstreamTokens:
        if not _credential(code):
            raise OAuthUpstreamError("invalid_request")
        # The official endpoint defines query parameters for the code and client
        # ID, but the secret belongs in multipart/form-data, never in the URL.
        payload = await self._request(
            "POST",
            TOKEN_URL,
            params={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._client_id,
            },
            files={"client_secret": (None, self._client_secret)},
        )
        return self._tokens(payload)

    async def refresh(self, refresh_token: str) -> UpstreamTokens:
        if not _credential(refresh_token):
            raise OAuthUpstreamError("invalid_grant")
        payload = await self._request(
            "POST",
            TOKEN_URL,
            params={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        return self._tokens(payload, previous_refresh=refresh_token)

    async def user(self, access_token: str) -> GitCodeIdentity:
        if not _credential(access_token):
            raise OAuthUpstreamError("invalid_grant")
        payload = await self._request(
            "GET", USER_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        raw_subject = payload.get("id")
        if isinstance(raw_subject, bool) or not isinstance(raw_subject, (str, int)):
            raise OAuthUpstreamError("invalid_response")
        subject = str(raw_subject)
        login = payload.get("login")
        if login is None or login == "":
            login = subject
        if not _identity(subject) or not _identity(login):
            raise OAuthUpstreamError("invalid_response")
        return GitCodeIdentity(subject, login)

    async def aclose(self) -> None:
        context_token = _credential_io.set(True)
        try:
            await self._client.aclose()
        finally:
            _credential_io.reset(context_token)
