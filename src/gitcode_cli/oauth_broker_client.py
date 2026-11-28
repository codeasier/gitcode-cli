"""One in-memory login against an independently trusted CLI broker (not the MCP service).

Internal only: the caller owns the terminal/browser UI and, before enabling login,
must verify the receipt with GitCode and provide secure expiry-aware storage.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import re
import secrets
import ssl
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import certifi
import httpx

from .config import valid_login
from .errors import AuthError

_ENTRY = "/cli/v1/browser"
_START = "/cli/v1/start"
_REDEEM = "/cli/v1/redeem"
_NONCE = re.compile(r"[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_AUTHORITY = re.compile(r"https://(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[1-9][0-9]{0,4})?")
_CA_PEM = re.compile(r"-----BEGIN CERTIFICATE-----\r?\n([A-Za-z0-9+/=\r\n]+)\r?\n-----END CERTIFICATE-----(?:\r?\n)?")
_MAX_CA_PEM = 16_384
_MAX_BODY = 16_384
_TOTAL_TIMEOUT = 300
_REQUEST_TIMEOUT = 8
_PRIVATE_IO: ContextVar[bool] = ContextVar("gc_broker_io", default=False)


class _NoPrivateIO(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: ARG002 - logging.Filter API
        # Even rejected response headers/reason phrases can contain a credential.
        return not _PRIVATE_IO.get()


_FILTER = _NoPrivateIO()


def _origin(value: str) -> str:
    # One canonical origin spelling only: never resolve browser_url, issuers or
    # endpoints against a server response; never read a broker from a repo/env.
    error = AuthError("Expected an independently trusted canonical HTTPS broker origin.")
    if type(value) is not str or len(value) > 300 or not _AUTHORITY.fullmatch(value):
        raise error
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        port = url.port
        if ":" in host or re.fullmatch(r"[0-9.]+", host):
            if str(ipaddress.ip_address(host)) != host:
                raise error
        elif (
            len(host) > 253
            or not all(_LABEL.fullmatch(label) for label in host.split("."))
            or re.fullmatch(r"(?:[0-9]+|0x[a-f0-9]+)", host.rsplit(".", 1)[-1])
        ):
            raise error
        if port == 443 or str(httpx.URL(value)) != value:
            raise error
    except (ValueError, httpx.InvalidURL):
        raise error from None
    return value


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def _bad_reply() -> AuthError:
    return AuthError("Invalid OAuth broker response. Start a new login; do not retry this transaction.")


@dataclass(frozen=True, repr=False)
class BrokerTrust:
    """Explicit owner-provisioned trust for one broker origin, never discovered from the broker or environment.

    ca_pem is a single in-memory CA certificate, not a file path, key or credential.
    It replaces (does not augment) the public CA set for this transaction only.
    """

    origin: str
    ca_pem: str


def _broker_context(origin: str, trust: BrokerTrust | None) -> ssl.SSLContext:
    # SSLContext(PROTOCOL_TLS_CLIENT) requires certificate + hostname verification.
    # Do not use create_default_context(): it can honor SSLKEYLOGFILE.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if trust is None:
        context.load_verify_locations(cafile=certifi.where())
        return context

    error = AuthError("Invalid explicit OAuth broker trust configuration.")
    if type(trust) is not BrokerTrust or type(trust.origin) is not str or trust.origin != origin:
        raise error
    pem = trust.ca_pem
    match = _CA_PEM.fullmatch(pem) if type(pem) is str and len(pem) <= _MAX_CA_PEM else None
    if match is None:
        raise error
    # Some TLS builds pre-seed even a newly allocated context; never silently add
    # the broker CA to that trust store or fall back to the public default.
    if any(context.cert_store_stats().values()):
        raise error
    encoded = match[1].replace("\r", "").replace("\n", "")
    try:
        der = base64.b64decode(encoded, validate=True)
        if base64.b64encode(der).decode("ascii") != encoded:
            raise error
        context.load_verify_locations(cadata=der)
    except (ValueError, ssl.SSLError):
        raise error from None
    # Only one complete CA, not a leaf, concatenated DER or trailing data.
    if context.get_ca_certs(binary_form=True) != [der]:
        raise error
    context.hostname_checks_common_name = False  # Explicit broker certificates must carry a matching SAN.
    return context


@dataclass(frozen=True, repr=False)
class BrokerReceipt:
    """Sensitive, one-time broker assertions; not yet a verified local credential."""

    access_token: str = field(repr=False)
    subject: str = field(repr=False)
    login: str = field(repr=False)
    expires_at: float


def _receipt(obj: dict) -> BrokerReceipt:
    if set(obj) != {"status", "access_token", "subject", "login", "expires_at"} or obj["status"] != "authorized":
        raise _bad_reply()
    token, subject, login, expires = (obj[k] for k in ("access_token", "subject", "login", "expires_at"))
    if (
        type(token) is not str
        or not 0 < len(token) <= 8192
        or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token)
        or type(subject) is not str
        or not 0 < len(subject) <= 512
        or not subject.isprintable()
        or any(c.isspace() for c in subject)
        or not valid_login(login)
        or token in subject
        or token in login
        or type(expires) not in (int, float)
        or not time.time() < expires <= 2**53
    ):
        raise _bad_reply()
    return BrokerReceipt(token, subject, login, expires)


def _pairing(obj: dict, origin: str, verifier: str) -> tuple[str, str]:
    if set(obj) != {"selector", "pairing", "browser_url"} or obj["browser_url"] != origin + _ENTRY:
        raise _bad_reply()
    selector, pair = obj["selector"], obj["pairing"]
    if type(selector) is not str or not _NONCE.fullmatch(selector) or type(pair) is not str:
        raise _bad_reply()
    parts = pair.split(".")
    if (
        len(parts) != 2
        or parts[0] != selector
        or not _NONCE.fullmatch(parts[1])
        or verifier in parts
        or parts[1] == selector
    ):
        raise _bad_reply()
    return selector, pair


async def _post(
    client: httpx.AsyncClient, url: str, fields: dict[str, str], statuses: tuple[int, ...]
) -> tuple[int, dict]:
    # Use a fresh explicit request: do not merge client headers, cookies or auth.
    request = httpx.Request(
        "POST",
        url,
        content=json.dumps(fields, separators=(",", ":")).encode("ascii"),
        headers={"Accept": "application/json", "Accept-Encoding": "identity", "Content-Type": "application/json"},
    )
    response = await client.send(request, stream=True, auth=None, follow_redirects=False)
    try:
        if response.status_code not in statuses:
            # No retry on any negative status, including 429/503; don't consume/echo its body.
            raise AuthError("OAuth broker did not approve this request. Start a new login.")
        headers = response.headers
        lengths = headers.get_list("content-length")
        if (
            len(headers.raw) > 64
            or sum(len(k) + len(v) for k, v in headers.raw) > 16_384
            or headers.get_list("content-type") != ["application/json"]
            or headers.get_list("content-encoding") not in ([], ["identity"])
            or "set-cookie" in headers
            or "location" in headers
            or "no-store" not in {part.strip().lower() for part in headers.get("cache-control", "").split(",")}
            or (
                lengths
                and (
                    len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,4}", lengths[0]) or int(lengths[0]) > _MAX_BODY
                )
            )
        ):
            raise _bad_reply()
        raw = bytearray()
        async for chunk in response.aiter_raw():
            if len(chunk) > _MAX_BODY - len(raw):
                raise _bad_reply()
            raw.extend(chunk)
        if lengths and len(raw) != int(lengths[0]):
            raise _bad_reply()
        try:
            obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        except (ValueError, RecursionError):
            raise _bad_reply() from None
        if type(obj) is not dict:
            raise _bad_reply()
        return response.status_code, obj
    finally:
        await response.aclose()


async def _run(
    origin: str,
    present: Callable[[str, str], Awaitable[None]],
    transport: httpx.AsyncBaseTransport | None,
    trust: BrokerTrust | None,
) -> BrokerReceipt:
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    # No proxy, netrc, ambient private CA env, retry or key-log configuration.
    if transport is None:
        transport = httpx.AsyncHTTPTransport(verify=_broker_context(origin, trust), trust_env=False, retries=0)
    deadline = asyncio.get_running_loop().time() + _TOTAL_TIMEOUT
    async with httpx.AsyncClient(trust_env=False, timeout=_REQUEST_TIMEOUT, transport=transport) as client:
        _, obj = await asyncio.wait_for(
            _post(client, origin + _START, {"challenge": challenge}, (201,)), _REQUEST_TIMEOUT
        )
        selector, pair = _pairing(obj, origin, verifier)
        # Caller may show pair on the originating terminal only, opening the clean URL separately.
        try:
            await present(origin + _ENTRY, pair)
        except Exception:
            raise AuthError("Unable to present the OAuth pairing request. Start a new login.") from None
        while True:
            if asyncio.get_running_loop().time() >= deadline:
                raise asyncio.TimeoutError
            status, obj = await asyncio.wait_for(
                _post(client, origin + _REDEEM, {"selector": selector, "verifier": verifier}, (200, 202)),
                _REQUEST_TIMEOUT,
            )
            if status == 200:
                return _receipt(obj)
            if obj != {"status": "pending", "retry_after": 5} or type(obj["retry_after"]) is not int:
                raise _bad_reply()
            await asyncio.sleep(5)


async def acquire_receipt(
    broker_origin: str,
    present: Callable[[str, str], Awaitable[None]],
    *,
    trust: BrokerTrust | None = None,
    _transport: httpx.AsyncBaseTransport | None = None,
) -> BrokerReceipt:
    """A new explicit transaction. Only an exact pending response on the pinned HTTPS origin permits another POST.

    Cancellation propagates and performs no further network action. Never retry this call
    automatically on timeout, disconnect, a lost receipt, or a failure to store it.
    Absent explicit trust, the original certifi roots apply. Explicit trust is only
    for the native TLS connection; it cannot be combined with a custom transport.
    The private transport seam is exclusively for offline tests, never user configuration.
    """
    origin = _origin(broker_origin)
    if trust is not None and _transport is not None:
        raise AuthError("Explicit OAuth broker trust cannot be combined with a test transport.")
    for name in ("httpx", "httpcore", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy"):
        logging.getLogger(name).addFilter(_FILTER)
    guard = _PRIVATE_IO.set(True)
    try:
        return await asyncio.wait_for(_run(origin, present, _transport, trust), _TOTAL_TIMEOUT)
    except AuthError:
        raise
    except Exception:
        # Do not let an HTTP/SSL or presentation exception surface proof material.
        raise AuthError("OAuth login did not complete; the outcome may be unknown. Start a new login.") from None
    finally:
        _PRIVATE_IO.reset(guard)
