"""Small HTTP checks around SDK OAuth routes and the MCP transport."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings
from .oauth import GitCodeOAuthProvider
from .oauth_store import OAuthStoreError


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if value == pattern:
            return True
        if pattern.endswith(":*"):
            base = pattern[:-2]
            if value == base or (value.startswith(base + ":") and value[len(base) + 1 :].isdigit()):
                return True
    return False


class OAuthHTTPBoundary:
    """Constrain all public routes, including routes outside SDK transport checks.

    Canonical OAuth URLs come from configuration, never Host/Forwarded headers.
    OAuth request bodies are buffered once with a small limit and replayed to the
    SDK, which still owns client authentication, PKCE, scopes, and protocol errors.
    """

    def __init__(self, app: ASGIApp, settings: Settings, provider: GitCodeOAuthProvider):
        self.app, self.settings, self.provider = app, settings, provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":

            async def lifecycle_send(message: dict) -> None:
                if message["type"] in {"lifespan.shutdown.complete", "lifespan.startup.failed"}:
                    await self.provider.aclose()
                await send(message)

            await self.app(scope, receive, lifecycle_send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def reject(status: int, error: str = "invalid_request") -> None:
            await JSONResponse(
                {"error": error}, status_code=status, headers={"Cache-Control": "no-store"}
            )(scope, receive, send)

        headers: dict[bytes, list[bytes]] = {}
        for name, value in scope.get("headers", []):
            headers.setdefault(name.lower(), []).append(value)
        if len(headers.get(b"host", [])) != 1 or not _matches(
            headers[b"host"][0].decode("latin-1"), self.settings.allowed_hosts
        ):
            await reject(421)
            return
        if any(
            len(headers.get(name, [])) > 1
            for name in (b"authorization", b"origin", b"content-type")
        ):
            await reject(400)
            return
        if b"origin" in headers and not _matches(
            headers[b"origin"][0].decode("latin-1"), self.settings.allowed_origins
        ):
            await reject(403)
            return
        path = scope["path"]
        is_oauth = path.startswith("/oauth/") or path in {"/authorize", "/token", "/revoke"}
        raw_query = scope.get("query_string", b"")
        if is_oauth:
            if len(raw_query) > 8192:
                await reject(414)
                return
            try:
                query = parse_qsl(
                    raw_query.decode("utf-8"), keep_blank_values=True, max_num_fields=40
                )
            except (UnicodeError, ValueError):
                await reject(400)
                return
            if len({key for key, _ in query}) != len(query):
                await reject(400)
                return
            if any(key in {"client_secret", "access_token", "refresh_token"} for key, _ in query):
                await reject(400)
                return

        downstream_receive = receive
        if is_oauth and scope["method"] == "POST":
            content_type = headers.get(b"content-type", [b""])[0].split(b";", 1)[0].strip().lower()
            if content_type != b"application/x-www-form-urlencoded":
                await reject(415)
                return
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 16384:
                    await reject(413)
                    return
                if not message.get("more_body", False):
                    break
            try:
                fields = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=40)
            except (UnicodeError, ValueError):
                await reject(400)
                return
            if len({key for key, _ in fields}) != len(fields):
                await reject(400)
                return
            form = dict(fields)
            if path == "/token":
                # MCP SDK 2.3.0 parses but does not enforce the token request's
                # resource indicator, so explicitly enforce it before delegation.
                if form.get("resource") != self.provider.config.resource_url:
                    await reject(400, "invalid_target")
                    return
                if form.get("grant_type") == "authorization_code" and not re.fullmatch(
                    r"[A-Za-z0-9._~-]{43,128}", form.get("code_verifier", "")
                ):
                    await reject(400)
                    return
            replayed = False

            async def replay() -> dict:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            downstream_receive = replay

        if path == "/.well-known/oauth-authorization-server" and scope["method"] == "GET":
            response = await self.provider.metadata(Request(scope, downstream_receive))
            await response(scope, downstream_receive, send)
            return
        response_started = False

        async def tracked_send(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, downstream_receive, tracked_send)
        except OAuthStoreError:
            # Storage exceptions intentionally carry no record bodies or keys.
            if not response_started:
                await reject(503, "temporarily_unavailable")
