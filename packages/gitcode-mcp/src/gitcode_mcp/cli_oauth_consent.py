"""Isolated CLI broker callback and consent. Not mounted on the MCP application.

Embedding requires a dedicated store/key, a registered HTTPS callback, a trusted
fixed-origin Bearer identity verifier and access/proxy/tracing logs that omit
OAuth query strings, cookies and bodies. No CLI verifier or token is sent to
the browser. The CLI start and redemption routes are intentionally absent.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl

import httpx
from starlette.requests import ClientDisconnect, Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from .cli_oauth_browser import _HEADERS, COOKIE, ENTRY, CLIBrowserEntry, _error
from .cli_oauth_flow import FlowRejected, Subject
from .oauth_store import OAuthStore, OAuthStoreError
from .oauth_upstream import GitCodeOAuthUpstream, OAuthUpstreamError

CALLBACK = "/cli/v1/callback"
CONSENT = "/cli/v1/consent"
FINISHED = "/cli/v1/finished"
_COOKIE = re.compile(r"([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})")
_CSRF = rb"[A-Za-z0-9_-]{43}"
_REPLIES = (
    re.compile(rb"csrf=(" + _CSRF + rb")&decision=(allow|deny)"),
    re.compile(rb"decision=(allow|deny)&csrf=(" + _CSRF + rb")"),
)
_CALLBACK_DEADLINE = 15.0
_FORM_DEADLINE = 5.0


def _binding(req: Request) -> tuple[str, str]:
    bindings = []
    for header in req.headers.getlist("cookie"):
        for part in header.split(";"):
            name, sep, value = part.strip().partition("=")
            if name == COOKIE:
                match = _COOKIE.fullmatch(value) if sep else None
                if not match:
                    raise FlowRejected()
                bindings.append(match.groups())
    if len(bindings) != 1:
        raise FlowRejected()
    return bindings[0]


def _callback_input(raw: bytes) -> tuple[str, str | None]:
    if not 1 <= len(raw) <= 4096 or re.search(rb"%(?![a-fA-F0-9]{2})", raw):
        raise FlowRejected()
    try:
        pairs = parse_qsl(
            raw.decode("ascii"),
            keep_blank_values=True,
            strict_parsing=True,
            errors="strict",
            max_num_fields=3,
        )
    except (ValueError, UnicodeError):
        raise FlowRejected() from None
    values = dict(pairs)
    if len(values) != len(pairs) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", values.get("state", "")):
        raise FlowRejected()
    if set(values) == {"state", "code"} and re.fullmatch(r"[!-~]{1,2048}", values["code"]):
        return values["state"], values["code"]
    if (
        set(values) in ({"state", "error"}, {"state", "error", "error_description"})
        and re.fullmatch(r"[a-z_]{1,64}", values["error"])
        and all(c.isprintable() for c in values.get("error_description", ""))
    ):
        return values["state"], None
    raise FlowRejected()


def _next(path: str, *, clear: bool = False) -> Response:
    res = RedirectResponse(path, status_code=303, headers=_HEADERS)
    if clear:
        res.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return res


class CLIBrowserConsent(CLIBrowserEntry):
    """Separate browser application; request data never chooses the OAuth registration."""

    def __init__(
        self,
        store: OAuthStore,
        *,
        broker_origin: str,
        client_id: str,
        client_secret: str,
        verify_identity: Callable[[str], Awaitable[Subject]],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            store, broker_origin=broker_origin, client_id=client_id, verify_identity=verify_identity
        )
        self._upstream = GitCodeOAuthUpstream(
            client_id, client_secret, self._origin + CALLBACK, transport=transport
        )

    async def aclose(self) -> None:
        await self._upstream.aclose()

    async def _handle(self, req: Request) -> Response:
        path = req.scope.get("path")
        if path == ENTRY:
            return await super()._handle(req)
        headers = req.scope.get("headers", [])
        if (
            path not in (CALLBACK, CONSENT, FINISHED)
            or req.scope.get("scheme") != "https"
            or len(headers) > 64
            or sum(len(k) + len(v) for k, v in headers) > 16384
            or req.headers.getlist("host") != [self._authority]
            or req.scope.get("root_path", "")
            or req.scope.get("raw_path", b"") != path.encode("ascii")
            or (path != CALLBACK and req.scope.get("query_string"))
        ):
            return _error()
        if path == FINISHED and req.method == "GET":
            # Identical after allow, denial, expiry or callback failure, no open redirect.
            return PlainTextResponse(
                "Return to your GitCode CLI to check the login result.", headers=_HEADERS
            )
        if path == CALLBACK and req.method == "GET":
            return await self._callback(req)
        if path != CONSENT or req.method not in {"GET", "POST"}:
            return _error()
        if not self._admit():
            return _error(429)
        decision_dispatched = False
        deadline = time.monotonic() + _FORM_DEADLINE
        try:
            selector, cookie = _binding(req)
            async with asyncio.timeout(deadline - time.monotonic()):
                if req.method == "GET":
                    view = await asyncio.to_thread(
                        self.flow.consent_view, selector, cookie, deadline=deadline
                    )
                    page = (
                        '<!doctype html><meta charset="utf-8"><title>Confirm GitCode CLI login</title>'
                        "<h1>Confirm GitCode CLI login</h1><p>Allow the CLI that you paired "
                        "to use this GitCode account? Only continue if you started that CLI.</p>"
                        f"<p>Login: <bdi>{html.escape(view.identity.login)}</bdi>; "
                        f"account ID: <bdi>{html.escape(view.identity.subject)}</bdi></p>"
                        f'<form method="post" action="{CONSENT}"><input type="hidden" name="csrf" '
                        f'value="{view.csrf}"><button name="decision" value="deny">Cancel</button>'
                        '<button name="decision" value="allow">Allow this CLI</button></form>'
                    )
                    return HTMLResponse(page, headers=_HEADERS)
                if (
                    req.headers.getlist("origin") != [self._origin]
                    or req.headers.getlist("content-type") != ["application/x-www-form-urlencoded"]
                    or req.headers.getlist("content-encoding")
                    or req.headers.getlist("content-length") not in ([], ["62"], ["63"])
                ):
                    return _error()
                raw = bytearray()
                async for part in req.stream():
                    if len(part) > 63 - len(raw):
                        return _error()
                    raw.extend(part)
                m = _REPLIES[0].fullmatch(raw)
                if m:
                    csrf, decision = m.groups()
                else:
                    m = _REPLIES[1].fullmatch(raw)
                    if not m:
                        return _error()
                    decision, csrf = m.groups()
                decision_dispatched = True
                await asyncio.to_thread(
                    self.flow.decide,
                    selector,
                    cookie,
                    csrf.decode("ascii"),
                    allow=decision == b"allow",
                    deadline=deadline,
                )
                return _next(FINISHED, clear=True)
        except (ClientDisconnect, FlowRejected):
            return _error()
        except (OAuthStoreError, TimeoutError):
            # Losing the worker acknowledgement is not a rejection: a commit
            # begun before the deadline might already have made the choice durable.
            # Keep the cookie unless we know the choice consumed the flow.
            return _next(FINISHED) if decision_dispatched else _error()

    async def _callback(self, req: Request) -> Response:
        # Every normal callback exit discards its sensitive query before displaying UI.
        if not self._admit():
            return _next(FINISHED)
        claimed = False
        deadline = time.monotonic() + _CALLBACK_DEADLINE
        try:
            selector, cookie = _binding(req)
            state, code = _callback_input(req.scope.get("query_string", b""))
            async with asyncio.timeout(deadline - time.monotonic()):
                claim = await asyncio.to_thread(
                    self.flow.claim_callback, selector, cookie, state, deadline=deadline
                )
                claimed = True
                if code is None:
                    # Valid denial consumes the callback. Remaining non-redeemable row expires.
                    return _next(FINISHED, clear=True)
                tokens = await self._upstream.exchange_code(code)
                await self.flow.complete_exchange(
                    selector, claim, tokens.access_token, tokens.expires_at, deadline=deadline
                )
                return _next(CONSENT)
        except (FlowRejected, OAuthStoreError, OAuthUpstreamError, TimeoutError):
            # A failed exchange has unknown upstream status; never retry it.
            return _next(FINISHED, clear=claimed)
