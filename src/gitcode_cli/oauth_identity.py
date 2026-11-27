"""Internal identity check for a freshly obtained GitCode OAuth access token.

This does not obtain, persist, or route the credential to any ordinary CLI command.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import ssl
from contextvars import ContextVar
from dataclasses import dataclass

import anyio
import certifi
import httpx

from ._redact import redact
from .config import valid_login
from .errors import APIError, AuthError, NetworkError

_URL = "https://api.gitcode.com/api/v5/user"
_MAX_BODY = 64 * 1024
_TOTAL_SECONDS = 8.0
_CLOSE_SECONDS = 0.5
_JSON_TYPE = re.compile(
    r'application/json(?:[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:"utf-8"|utf-8))?', re.IGNORECASE | re.ASCII
)
_PRIVATE = ContextVar("gc_private_oauth_identity_io", default=False)


class _PrivateIOFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: ARG002 - logging.Filter API
        # Rejected reason phrases and response headers can contain arbitrary secrets.
        return not _PRIVATE.get()


_FILTER = _PrivateIOFilter()


@dataclass(frozen=True)
class OAuthIdentity:
    subject: str
    login: str


def _invalid() -> APIError:
    return APIError("Invalid GitCode OAuth identity response.")


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def _finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def _integer(value: str) -> int:
    # Bound integer conversion on Python versions without an interpreter digit cap.
    if len(value) > 128:
        raise ValueError
    return int(value)


def _json(body: bytearray) -> object:
    try:
        obj = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_int=_integer,
            parse_float=_finite,
            parse_constant=_finite,
        )
        # json.loads accepts lone surrogate escapes. Require actual Unicode scalar
        # strings even in ignored fields/keys, not only in the extracted identity.
        pending = [obj]
        while pending:
            node = pending.pop()
            if isinstance(node, str):
                node.encode("utf-8")
            elif isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                pending.extend(node)
                pending.extend(node.values())
        return obj
    except (ValueError, RecursionError):
        raise _invalid() from None


def _headers(response: httpx.Response) -> int | None:
    if response.status_code != 200:
        raise APIError(f"GitCode OAuth identity API returned HTTP {response.status_code}.", response.status_code)
    headers = response.headers
    if len(headers.raw) > 64 or sum(len(k) + len(v) for k, v in headers.raw) > 16_384:
        raise _invalid()
    if headers.get("content-encoding", "identity").lower() != "identity" or not _JSON_TYPE.fullmatch(
        headers.get("content-type", "").strip()
    ):
        raise _invalid()
    lengths = headers.get_list("content-length")
    if not lengths:
        return None
    if (
        "transfer-encoding" in headers
        or len(lengths) != 1
        or not re.fullmatch(r"0|[1-9][0-9]{0,4}", lengths[0])
        or int(lengths[0]) > _MAX_BODY
    ):
        raise _invalid()
    return int(lengths[0])


def _transport() -> httpx.AsyncHTTPTransport:
    # ssl.create_default_context() can consult SSLKEYLOGFILE even when trust_env=False.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    return httpx.AsyncHTTPTransport(verify=context, trust_env=False, retries=0)


async def _profile(token: str) -> object:
    # This budget includes resolution, TLS, receipt of the headers and the whole body.
    # Synchronous CPU/OS work cannot be preempted; recheck the clock before success.
    deadline = anyio.current_time() + _TOTAL_SECONDS
    client = httpx.AsyncClient(transport=_transport(), timeout=_TOTAL_SECONDS, trust_env=False, follow_redirects=False)
    response = None
    completed = False
    try:
        remaining = deadline - anyio.current_time()
        if remaining <= 0:
            raise TimeoutError
        with anyio.fail_after(remaining):
            request = httpx.Request(
                "GET",
                _URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Authorization": f"Bearer {token}",
                },
            )
            response = await client.send(request, stream=True, auth=None, follow_redirects=False)
            expected = _headers(response)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(chunk) > _MAX_BODY - len(body):
                    raise _invalid()
                body.extend(chunk)
            if expected is not None and len(body) != expected:
                raise _invalid()
            obj = _json(body)
            if anyio.current_time() >= deadline:
                raise TimeoutError
            completed = True
            return obj
    finally:
        # One separate, bounded best-effort close budget; always attempt the transport close.
        close_by = anyio.current_time() + _CLOSE_SECONDS
        try:
            if response is not None:
                with anyio.move_on_after(_CLOSE_SECONDS / 2, shield=True):
                    await response.aclose()
        finally:
            with anyio.move_on_after(max(0.0, close_by - anyio.current_time()), shield=True) as closing:
                await client.aclose()
        if completed and closing.cancel_called:
            raise NetworkError("Could not finish closing the GitCode OAuth identity transport.")


async def _finish(loop: asyncio.AbstractEventLoop, task: asyncio.Task, budget: float) -> None:
    # Unlike asyncio.run(), finish async-generator cleanup without joining the
    # executor. Early size rejection may leave HTTPX's nested iterators to close.
    with anyio.move_on_after(budget):
        if not task.done():
            task.cancel()
            await asyncio.wait({task})
            if task.done() and not task.cancelled():
                task.exception()
        await loop.shutdown_asyncgens()


def _read_profile(token: str) -> object:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise NetworkError("OAuth identity verification requires a synchronous caller or worker.")
    for name in ("httpx", "httpcore", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy"):
        logging.getLogger(name).addFilter(_FILTER)
    # asyncio.run() waits for the default executor on shutdown. Do not let an OS
    # resolver that outlives cancellation hold this sync call; DNS may finish later.
    loop = asyncio.new_event_loop()
    guard = _PRIVATE.set(True)
    hard_by = loop.time() + _TOTAL_SECONDS + _CLOSE_SECONDS
    task = loop.create_task(_profile(token))
    try:
        return loop.run_until_complete(task)
    except (OSError, httpx.HTTPError, httpx.StreamError):
        raise NetworkError("Could not read the GitCode OAuth identity response.") from None
    finally:
        try:
            # A main-thread interruption can unwind run_until_complete while
            # the coroutine still owns a socket. Give its finally block a chance.
            budget = max(0.0, min(_CLOSE_SECONDS, hard_by - loop.time()))
            loop.run_until_complete(_finish(loop, task, budget))
        finally:
            loop.close()
            _PRIVATE.reset(guard)


def verify_oauth_identity(access_token: str) -> OAuthIdentity:
    """Read the authenticated subject and login; never derive either from the other."""
    if (
        type(access_token) is not str
        or not 0 < len(access_token) <= 8192
        or not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", access_token)
    ):
        raise AuthError("Invalid GitCode OAuth access token.")
    profile = _read_profile(access_token)
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
