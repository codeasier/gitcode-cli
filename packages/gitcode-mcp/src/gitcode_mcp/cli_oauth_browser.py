"""Standalone browser entry for CLI pairing, intentionally not mounted by the MCP server.

The embedding CLI broker must own a separate store/key and OAuth app registration.
A CLI command that created a transaction displays its selector and one-use browser
start proof as a single pairing string. The browser never receives the CLI verifier.
"""

from __future__ import annotations

import asyncio
import html
import re
import threading
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode, urlsplit

from starlette.requests import ClientDisconnect, Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.types import Receive, Scope, Send

from .cli_oauth_flow import CLIFlow, FlowRejected, Subject
from .oauth_config import https_url
from .oauth_store import OAuthStore, OAuthStoreError
from .oauth_upstream import AUTHORIZE_URL

ENTRY = "/cli/v1/browser"
COOKIE = "__Host-gc-cli-flow"
_PAIR = re.compile(rb"pair=([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})")
_PAIR_LENGTH = 92
_READ_DEADLINE = 5.0
_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
_FORM = (
    '<!doctype html><meta charset="utf-8"><title>Pair GitCode CLI</title>'
    "<h1>Pair this browser with your GitCode CLI</h1>"
    "<p>Only enter the pairing value shown by the login command you started on your own device. "
    "Do not enter a value sent by another person. Never enter an API token or password.</p>"
    f'<form action="{ENTRY}" method="post" autocomplete="off">'
    '<label>CLI pairing value <input name="pair" type="password" required '
    'minlength="87" maxlength="87" autocomplete="off" spellcheck="false"></label>'
    '<button type="submit">Pair browser</button></form>'
)


def _error(status: int = 400) -> Response:
    return PlainTextResponse("CLI authorization transaction unavailable.", status, headers=_HEADERS)


class CLIBrowserEntry:
    """One standalone ASGI app, one trusted origin, one unambiguous OAuth registration."""

    def __init__(
        self,
        store: OAuthStore,
        *,
        broker_origin: str,
        client_id: str,
        verify_identity: Callable[[str], Awaitable[Subject]],
    ) -> None:
        self.flow = CLIFlow(
            store, broker_origin=broker_origin, client_id=client_id, verify_identity=verify_identity
        )
        self._origin = https_url(broker_origin, "CLI broker origin", origin=True)
        self._authority = urlsplit(self._origin).netloc
        self._client_id = client_id
        self._lock = threading.Lock()
        self._reset = 0.0
        self._starts = 0

    def _admit(self) -> bool:
        # Bounded memory independent of client-supplied IP, Cookie or selector.
        # Single broker instance. An outer service must enforce deployment-wide limits.
        with self._lock:
            now = time.monotonic()
            if now >= self._reset:
                self._starts = 0
                self._reset = now + 60
            if self._starts >= 60:
                return False
            self._starts += 1
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            raise RuntimeError("HTTP endpoint only.")
        req = Request(scope, receive)
        response = await self._handle(req)
        await response(scope, receive, send)

    async def _handle(self, req: Request) -> Response:
        headers = req.scope.get("headers", [])
        if len(headers) > 64 or sum(len(k) + len(v) for k, v in headers) > 16_384:
            return _error()
        if (
            req.scope.get("scheme") != "https"
            or req.headers.getlist("host") != [self._authority]
            or req.scope.get("path") != ENTRY
            or req.scope.get("raw_path", ENTRY.encode()) != ENTRY.encode()
            or req.scope.get("root_path", "")
            or req.scope.get("query_string")
        ):
            return _error()
        if req.method == "GET":
            return HTMLResponse(_FORM, headers=_HEADERS)
        if (
            req.method != "POST"
            or req.headers.getlist("origin") != [self._origin]
            or req.headers.getlist("content-type") != ["application/x-www-form-urlencoded"]
            or req.headers.getlist("content-length") not in ([], [str(_PAIR_LENGTH)])
            or req.headers.getlist("content-encoding")
            or any(
                item.strip().partition("=")[0] == COOKIE
                for value in req.headers.getlist("cookie")
                for item in value.split(";")
            )
        ):
            return _error()
        if not self._admit():
            return _error(429)
        try:
            async with asyncio.timeout(_READ_DEADLINE):
                raw = bytearray()
                async for part in req.stream():
                    if len(part) > _PAIR_LENGTH - len(raw):
                        return _error()
                    raw.extend(part)
                pair = _PAIR.fullmatch(raw)
                if not pair:
                    return _error()
                selector, start = (part.decode("ascii") for part in pair.groups())
                binding = await asyncio.to_thread(self.flow.begin, selector, start)
        except (ClientDisconnect, FlowRejected, OAuthStoreError, TimeoutError):
            # Do not retry an uncertain begin after losing the caller or the deadline.
            return _error()
        target = (
            AUTHORIZE_URL
            + "?"
            + urlencode(
                {
                    "client_id": self._client_id,
                    "redirect_uri": self._origin + "/cli/v1/callback",
                    "response_type": "code",
                    "state": binding.upstream_state,
                    "prompt": "consent",
                }
            )
        )
        safe = html.escape(target, quote=True)
        # A cross-origin 303 on a browser form POST is blocked by Chromium's
        # form-action policy. A fresh top-level GET is not a form submission.
        page = (
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" '
            f'content="0;url={safe}"><title>Continue to GitCode</title>'
            f'<a rel="noreferrer" href="{safe}">Continue to GitCode</a>'
        )
        response = HTMLResponse(page, headers=_HEADERS)
        response.set_cookie(
            COOKIE,
            selector + "." + binding.cookie,
            max_age=300,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response
