"""GitCode login broker implementing the MCP SDK's OAuth provider contract.

GitCode credentials stay encrypted on this host. MCP clients receive independent
opaque tokens bound to one authorization, user, client, resource, and scope set.
"""

from __future__ import annotations

import hashlib
import html
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import anyio
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from .api import GitCodeError
from .config import Settings
from .oauth_config import READ_SCOPE, WRITE_SCOPE, OAuthSettings
from .oauth_store import OAuthStore, OAuthStoreError
from .oauth_upstream import GitCodeOAuthUpstream, OAuthUpstreamError, UpstreamTokens

AUTH_TTL = 600
CODE_TTL = 120
ACCESS_TTL = 900
GRANT_TTL = 30 * 86400
COOKIE_NAME = "__Host-gitcode-oauth"
OPAQUE = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
}


def _nonce() -> str:
    return secrets.token_urlsafe(32)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _token_data(tokens: UpstreamTokens) -> dict[str, Any]:
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
        "scope": tokens.scope,
    }


class BrokerCode(AuthorizationCode):
    code: str = Field(repr=False)
    grant_id: str


class BrokerAccessToken(AccessToken):
    token: str = Field(repr=False)
    grant_id: str


class BrokerRefreshToken(RefreshToken):
    token: str = Field(repr=False)
    grant_id: str


class GitCodeOAuthProvider(
    OAuthAuthorizationServerProvider[BrokerCode, BrokerRefreshToken, BrokerAccessToken]
):
    def __init__(
        self,
        settings: Settings,
        *,
        store: OAuthStore | None = None,
        upstream: GitCodeOAuthUpstream | None = None,
    ) -> None:
        if settings.oauth is None:
            raise ValueError("OAuth settings are required.")
        self.settings = settings
        self.config: OAuthSettings = settings.oauth
        self.store = store or OAuthStore(self.config.database, self.config.encryption_key)
        self.upstream = upstream or GitCodeOAuthUpstream(
            self.config.gitcode_client_id,
            self.config.gitcode_client_secret,
            self.config.callback_url,
            scopes=self.config.gitcode_scopes,
            timeout=settings.timeout,
        )
        # The supported deployment has one worker. Serialize upstream rotation so
        # concurrent MCP requests never redeem the same GitCode refresh token.
        self._refresh_lock = anyio.Lock()
        self._closed = False
        self.scopes = [READ_SCOPE] + ([] if settings.read_only else [WRITE_SCOPE])
        self.client = OAuthClientInformationFull(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            client_name="ChatGPT GitCode",
            redirect_uris=list(self.config.redirect_uris),
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self.scopes),
        )

    @property
    def auth_settings(self) -> AuthSettings:
        return AuthSettings(
            issuer_url=self.config.public_url,
            resource_server_url=self.config.resource_url,
            validate_token_resource=True,
            required_scopes=[READ_SCOPE],
            client_registration_options=ClientRegistrationOptions(
                enabled=False, valid_scopes=self.scopes, default_scopes=self.scopes
            ),
            revocation_options=RevocationOptions(enabled=True),
        )

    @property
    def challenge(self) -> str:
        return (
            'Bearer error="invalid_token", resource_metadata="'
            + self.config.public_url
            + '/.well-known/oauth-protected-resource/mcp"'
        )

    async def metadata(self, request: Request) -> Response:
        options = self.auth_settings
        metadata = build_metadata(
            options.issuer_url,
            None,
            options.client_registration_options,
            options.revocation_options,
        ).model_dump(mode="json", exclude_none=True)
        # This pre-registered client uses POST credentials. Do not advertise the
        # SDK's Basic method, whose client_id handling is not suitable here.
        metadata["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
        metadata["revocation_endpoint_auth_methods_supported"] = ["client_secret_post"]
        return JSONResponse(metadata, headers={"Cache-Control": "no-store"})

    def routes(self) -> list[Route]:
        return [
            Route("/oauth/start", self.start, methods=["GET"]),
            Route("/oauth/gitcode/callback", self.callback, methods=["GET"]),
            Route("/oauth/consent", self.consent, methods=["GET", "POST"]),
        ]

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.client if client_id == self.config.client_id else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("Dynamic client registration is disabled.")

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource != self.config.resource_url:
            raise AuthorizeError("invalid_target", "Request this MCP server's resource URL.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.code_challenge):
            raise AuthorizeError("invalid_request", "A valid S256 PKCE challenge is required.")
        scopes = params.scopes if params.scopes is not None else self.scopes
        if READ_SCOPE not in scopes or not set(scopes).issubset(self.scopes):
            raise AuthorizeError("invalid_scope", "Request an available GitCode MCP scope.")
        flow = _nonce()
        deadline = time.time() + AUTH_TTL
        payload = {
            **params.model_dump(mode="json"),
            "client_id": client.client_id,
            "scopes": scopes,
            "expires_at": deadline,
        }
        try:
            self.store.put("flow", flow, payload, deadline)
        except OAuthStoreError:
            raise AuthorizeError(
                "temporarily_unavailable", "Authorization is temporarily unavailable."
            ) from None
        return self.config.public_url + "/oauth/start?" + urlencode({"flow": flow})

    @staticmethod
    def _error_page(
        message: str = "Authorization expired or is invalid. Start a new connection.",
        status: int = 400,
    ) -> Response:
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            "<title>GitCode authorization</title><h1>GitCode authorization</h1><p>"
            + html.escape(message)
            + "</p></html>",
            status_code=status,
            headers=PAGE_HEADERS,
        )

    @staticmethod
    def _browser_matches(request: Request, record: dict[str, Any]) -> bool:
        cookie = request.cookies.get(COOKIE_NAME, "")
        return bool(OPAQUE.fullmatch(cookie)) and secrets.compare_digest(
            _digest(cookie), record.get("browser", "")
        )

    def _redirect(self, record: dict[str, Any], **params: str) -> Response:
        from mcp.server.auth.provider import construct_redirect_uri

        if record.get("state") is not None:
            params["state"] = record["state"]
        return RedirectResponse(
            construct_redirect_uri(record["redirect_uri"], **params),
            status_code=303,
            headers=PAGE_HEADERS,
        )

    async def start(self, request: Request) -> Response:
        flow = request.query_params.get("flow", "")
        if not OPAQUE.fullmatch(flow):
            return self._error_page()
        cookie = request.cookies.get(COOKIE_NAME, "")
        if not OPAQUE.fullmatch(cookie):
            cookie = _nonce()
        state = _nonce()
        with self.store.transaction() as tx:
            record = tx.pop("flow", flow)
            if record is None:
                return self._error_page()
            record["browser"] = _digest(cookie)
            tx.put("state", state, record, record["expires_at"])
        response = RedirectResponse(
            self.upstream.authorization_url(state), status_code=303, headers=PAGE_HEADERS
        )
        response.set_cookie(
            COOKIE_NAME,
            cookie,
            max_age=AUTH_TTL,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    async def callback(self, request: Request) -> Response:
        state = request.query_params.get("state", "")
        if not OPAQUE.fullmatch(state):
            return self._error_page()
        with self.store.transaction() as tx:
            record = tx.get("state", state)
            if record is None or not self._browser_matches(request, record):
                return self._error_page()
            tx.delete("state", state)
        if request.query_params.get("error"):
            return self._redirect(
                record,
                error="access_denied",
                error_description="GitCode authorization was declined.",
            )
        code = request.query_params.get("code", "")
        if not code or len(code) > 4096 or any(c.isspace() or ord(c) < 32 for c in code):
            return self._error_page()
        try:
            tokens = await self.upstream.exchange_code(code)
            identity = await self.upstream.user(tokens.access_token)
        except OAuthUpstreamError:
            return self._error_page(
                "GitCode authorization could not be completed. Start a new connection.", 502
            )
        if not self._allowed(identity.subject):
            return self._redirect(
                record,
                error="access_denied",
                error_description="This GitCode account is not allowed on this server.",
            )
        consent = _nonce()
        record.update(
            subject=identity.subject,
            login=identity.login,
            upstream=_token_data(tokens),
            csrf=_nonce(),
        )
        self.store.put("consent", consent, record, record["expires_at"])
        return RedirectResponse(
            self.config.public_url + "/oauth/consent?" + urlencode({"flow": consent}),
            status_code=303,
            headers=PAGE_HEADERS,
        )

    async def consent(self, request: Request) -> Response:
        form = await request.form() if request.method == "POST" else request.query_params
        flow = str(form.get("flow", ""))
        if not OPAQUE.fullmatch(flow):
            return self._error_page()
        if request.method == "GET":
            record = self.store.get("consent", flow)
            if record is None or not self._browser_matches(request, record):
                return self._error_page()
            escape = html.escape
            actions = "read repository data" + (
                ", create, replace and delete repository files, publish code commits, "
                "and manage issues, branches and pull requests"
                if WRITE_SCOPE in record["scopes"]
                else ""
            )
            repositories = (
                ", ".join(self.settings.allowed_repositories)
                or "repositories accessible to your GitCode account"
            )
            return HTMLResponse(
                '<!doctype html><html lang="en"><meta charset="utf-8"><title>Connect GitCode</title>'
                "<h1>Connect GitCode to ChatGPT</h1><p>GitCode account: <strong>"
                + escape(record["login"])
                + "</strong> ("
                + escape(record["subject"])
                + ")</p>"
                + "<p>Allow client <strong>"
                + escape(record["client_id"])
                + "</strong> to "
                + actions
                + " through "
                + escape(self.config.resource_url)
                + "?</p>"
                + "<p>Repository scope: "
                + escape(repositories)
                + "</p>"
                + '<form method="post" action="'
                + escape(self.config.public_url + "/oauth/consent", quote=True)
                + '">'
                + '<input type="hidden" name="flow" value="'
                + escape(flow, quote=True)
                + '">'
                + '<input type="hidden" name="csrf" value="'
                + escape(record["csrf"], quote=True)
                + '">'
                + '<button name="decision" value="allow">Allow access</button> '
                + '<button name="decision" value="deny">Cancel</button></form></html>',
                headers=PAGE_HEADERS,
            )
        if request.headers.get("origin") != self.config.public_url:
            return self._error_page("Invalid authorization confirmation.", 403)
        authorization_code = _nonce()
        grant_id = _nonce()
        with self.store.transaction() as tx:
            record = tx.get("consent", flow)
            if (
                record is None
                or not self._browser_matches(request, record)
                or not OPAQUE.fullmatch(str(form.get("csrf", "")))
                or not secrets.compare_digest(str(form.get("csrf", "")), record["csrf"])
                or form.get("decision") not in {"allow", "deny"}
            ):
                return self._error_page("Invalid authorization confirmation.", 403)
            tx.delete("consent", flow)
            if form["decision"] == "deny" or not self._allowed(record["subject"]):
                return self._redirect(
                    record, error="access_denied", error_description="Authorization was declined."
                )
            deadline = time.time() + GRANT_TTL
            grant = {
                "client_id": record["client_id"],
                "subject": record["subject"],
                "login": record["login"],
                "resource": self.config.resource_url,
                "scopes": record["scopes"],
                "upstream": record["upstream"],
                "expires_at": deadline,
            }
            tx.put("grant", grant_id, grant, deadline)
            code_record = {
                key: record[key]
                for key in (
                    "client_id",
                    "subject",
                    "resource",
                    "scopes",
                    "code_challenge",
                    "redirect_uri",
                    "redirect_uri_provided_explicitly",
                )
            }
            code_record.update(grant_id=grant_id, expires_at=time.time() + CODE_TTL)
            tx.put("code", authorization_code, code_record, code_record["expires_at"])
        return self._redirect(record, code=authorization_code)

    def _allowed(self, subject: str) -> bool:
        return not self.config.allowed_user_ids or subject in self.config.allowed_user_ids

    def _grant(self, grant_id: str, tx: Any | None = None) -> dict[str, Any] | None:
        record = (tx or self.store).get("grant", grant_id)
        if (
            record is None
            or record["client_id"] != self.config.client_id
            or record["resource"] != self.config.resource_url
            or not self._allowed(record["subject"])
        ):
            return None
        return record

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> BrokerCode | None:
        record = self.store.get("code", authorization_code)
        if (
            record is None
            or record["client_id"] != client.client_id
            or not self._grant(record["grant_id"])
        ):
            return None
        return BrokerCode(code=authorization_code, **record)

    def _issue(
        self, tx: Any, grant_id: str, grant: dict[str, Any], scopes: list[str]
    ) -> OAuthToken:
        access, refresh = _nonce(), _nonce()
        now = int(time.time())
        expires_at = min(now + ACCESS_TTL, int(grant["expires_at"]))
        base = {
            "grant_id": grant_id,
            "subject": grant["subject"],
            "client_id": grant["client_id"],
            "resource": grant["resource"],
            "scopes": scopes,
        }
        tx.put("access", access, {**base, "expires_at": expires_at}, expires_at)
        tx.put(
            "refresh",
            refresh,
            {**base, "expires_at": int(grant["expires_at"])},
            grant["expires_at"],
        )
        return OAuthToken(
            access_token=access,
            refresh_token=refresh,
            expires_in=expires_at - now,
            scope=" ".join(scopes),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: BrokerCode
    ) -> OAuthToken:
        with self.store.transaction() as tx:
            code = tx.pop("code", authorization_code.code)
            grant = self._grant(authorization_code.grant_id, tx)
            if code is None or grant is None or code["client_id"] != client.client_id:
                raise TokenError("invalid_grant", "Authorization code is no longer valid.")
            return self._issue(tx, authorization_code.grant_id, grant, code["scopes"])

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> BrokerRefreshToken | None:
        with self.store.transaction() as tx:
            reused = tx.get("used_refresh", refresh_token)
            if reused is not None and reused["client_id"] == client.client_id:
                tx.delete("grant", reused["grant_id"])
                return None
            record = tx.get("refresh", refresh_token)
            if (
                record is None
                or record["client_id"] != client.client_id
                or not self._grant(record["grant_id"], tx)
            ):
                return None
        return BrokerRefreshToken(token=refresh_token, **record)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: BrokerRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        result = None
        with self.store.transaction() as tx:
            record = tx.pop("refresh", refresh_token.token)
            grant = self._grant(refresh_token.grant_id, tx)
            if (
                record is not None
                and grant is not None
                and record["client_id"] == client.client_id
                and set(scopes).issubset(record["scopes"])
                and READ_SCOPE in scopes
            ):
                tx.put(
                    "used_refresh",
                    refresh_token.token,
                    {
                        "grant_id": refresh_token.grant_id,
                        "client_id": client.client_id,
                    },
                    grant["expires_at"],
                )
                result = self._issue(tx, refresh_token.grant_id, grant, scopes)
            else:
                reused = tx.get("used_refresh", refresh_token.token)
                if reused is not None and reused["client_id"] == client.client_id:
                    tx.delete("grant", reused["grant_id"])
        if result is None:
            raise TokenError(
                "invalid_grant", "Refresh token is no longer valid. Reconnect the account."
            )
        return result

    async def load_access_token(self, token: str) -> BrokerAccessToken | None:
        if not OPAQUE.fullmatch(token):
            return None
        record = self.store.get("access", token)
        if record is None or not self._grant(record["grant_id"]):
            return None
        return BrokerAccessToken(
            token=token, claims={"iss": str(AnyHttpUrl(self.config.public_url))}, **record
        )

    async def revoke_token(self, token: BrokerAccessToken | BrokerRefreshToken) -> None:
        self.store.delete("grant", token.grant_id)

    @staticmethod
    def _reauthorize() -> GitCodeError:
        return GitCodeError(
            "authentication_required",
            "Reconnect your GitCode account to authorize this MCP connection.",
        )

    async def upstream_access_token(self, token: AccessToken | None) -> str:
        if not isinstance(token, BrokerAccessToken):
            raise self._reauthorize()
        async with self._refresh_lock:
            current = await self.load_access_token(token.token)
            grant = self._grant(token.grant_id) if current else None
            if grant is None:
                raise self._reauthorize()
            upstream = grant["upstream"]
            if upstream["expires_at"] > time.time() + 60:
                return upstream["access_token"]
            if not upstream["refresh_token"]:
                await self.revoke_token(token)
                raise self._reauthorize()
            try:
                refreshed = await self.upstream.refresh(upstream["refresh_token"])
                identity = await self.upstream.user(refreshed.access_token)
            except OAuthUpstreamError as exc:
                if exc.code in {"invalid_grant", "authentication_failed", "permission_denied"}:
                    await self.revoke_token(token)
                    raise self._reauthorize() from None
                raise GitCodeError(
                    "oauth_upstream_error",
                    "GitCode authorization refresh is temporarily unavailable. Try again later.",
                ) from None
            if identity.subject != grant["subject"]:
                await self.revoke_token(token)
                raise self._reauthorize()
            with self.store.transaction() as tx:
                latest = self._grant(token.grant_id, tx)
                if latest is None:
                    raise self._reauthorize()
                latest["upstream"] = _token_data(refreshed)
                tx.put("grant", token.grant_id, latest, latest["expires_at"])
            return refreshed.access_token

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                await self.upstream.aclose()
            finally:
                self.store.close()
