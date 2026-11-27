"""CLI-side routes of the standalone OAuth broker. Never mount on the MCP app."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable

import httpx
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from .cli_oauth_browser import _HEADERS, ENTRY
from .cli_oauth_consent import CLIBrowserConsent
from .cli_oauth_flow import FlowPending, FlowRejected, Subject
from .oauth_store import OAuthStore, OAuthStoreError

START = "/cli/v1/start"
REDEEM = "/cli/v1/redeem"
_BUDGET = 5.0
_REPLY_RESERVE = 0.1
_LENGTH = re.compile(r"[1-9][0-9]{0,2}")
_VALUE = re.compile(r"[A-Za-z0-9_-]{43}")
_LIMIT = 256


def _answer(http_status: int, **fields: object) -> JSONResponse:
    return JSONResponse(fields, http_status, headers=_HEADERS)


def _unavailable(code: int = 400) -> JSONResponse:
    return _answer(code, status="unavailable")


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise FlowRejected()
    return result


async def _fields(req: Request, length: int, keys: set[str], deadline: float) -> dict[str, str]:
    raw = bytearray()
    fragments = 0
    async for part in req.stream():
        fragments += 1
        if time.monotonic() >= deadline:
            raise TimeoutError()
        if fragments > _LIMIT + 1 or len(part) > length - len(raw):
            raise FlowRejected()
        raw.extend(part)
    if len(raw) != length:
        raise FlowRejected()
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError):
        raise FlowRejected() from None
    if (
        type(obj) is not dict
        or set(obj) != keys
        or not all(type(v) is str and _VALUE.fullmatch(v) for v in obj.values())
    ):
        raise FlowRejected()
    return obj


class CLIOAuthBroker(CLIBrowserConsent):
    """One fixed-origin CLI OAuth application, not an MCP login or a device grant."""

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
            store,
            broker_origin=broker_origin,
            client_id=client_id,
            client_secret=client_secret,
            verify_identity=verify_identity,
            transport=transport,
        )
        # Fixed buckets; never key memory, limits or identities on untrusted IP/selector.
        # Browser admissions have their own bucket, so CLI polling cannot spend it.
        self._api_reset = 0.0
        self._api_counts = {START: 0, REDEEM: 0}

    def _admit_api(self, path: str) -> bool:
        with self._lock:
            now = time.monotonic()
            if now >= self._api_reset:
                self._api_counts = {START: 0, REDEEM: 0}
                self._api_reset = now + 60
            if self._api_counts[path] >= (20 if path == START else 120):
                return False
            self._api_counts[path] += 1
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in (START, REDEEM):
            return await super().__call__(scope, receive, send)
        end = time.monotonic() + _BUDGET
        deadline = end - _REPLY_RESERVE
        # Reserve only the tail of the same budget for the response. Never send a second
        # response or retry a mutation if transmission fails after commit.
        async with asyncio.timeout(end - time.monotonic()):
            try:
                async with asyncio.timeout(deadline - time.monotonic()):
                    response = await self._cli(Request(scope, receive), deadline)
                    if time.monotonic() >= deadline:
                        raise TimeoutError()
            except FlowPending:
                response = _answer(202, status="pending", retry_after=5)
            except (ClientDisconnect, FlowRejected):
                response = _unavailable()
            except (OAuthStoreError, TimeoutError):
                response = _unavailable(503)
            await response(scope, receive, send)

    async def _cli(self, req: Request, deadline: float) -> JSONResponse:
        scope, path = req.scope, req.scope["path"]
        headers = scope.get("headers", [])
        if (
            req.method != "POST"
            or scope.get("scheme") != "https"
            or scope.get("raw_path") != path.encode("ascii")
            or scope.get("root_path", "")
            or scope.get("query_string")
            or len(headers) > 64
            or sum(len(k) + len(v) for k, v in headers) > 16384
            or req.headers.getlist("host") != [self._authority]
            or req.headers.getlist("content-type") != ["application/json"]
            or any(
                req.headers.getlist(key)
                for key in (
                    "origin",
                    "referer",
                    "cookie",
                    "authorization",
                    "proxy-authorization",
                    "transfer-encoding",
                    "content-encoding",
                )
            )
        ):
            return _unavailable()
        sizes = req.headers.getlist("content-length")
        if len(sizes) != 1 or not _LENGTH.fullmatch(sizes[0]) or int(sizes[0]) > _LIMIT:
            return _unavailable()
        if not self._admit_api(path):
            return _unavailable(429)
        if path == START:
            body = await _fields(req, int(sizes[0]), {"challenge"}, deadline)
            start = await asyncio.to_thread(self.flow.create, body["challenge"], deadline=deadline)
            return _answer(
                201,
                selector=start.selector,
                pairing=start.selector + "." + start.browser_start,
                browser_url=self._origin + ENTRY,
            )
        body = await _fields(req, int(sizes[0]), {"selector", "verifier"}, deadline)
        result = await asyncio.to_thread(
            self.flow.redeem, body["selector"], body["verifier"], deadline=deadline
        )
        if result.expires_at <= time.time():
            return _unavailable()
        return _answer(
            200,
            status="authorized",
            access_token=result.access_token,
            expires_at=result.expires_at,
            subject=result.identity.subject,
            login=result.identity.login,
        )
