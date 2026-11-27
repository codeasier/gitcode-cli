"""Opt-in, direct loopback-TLS service for the *CLI* GitCode OAuth application."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import ssl
import stat
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
import uvicorn
from cryptography.fernet import Fernet
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from .cli_oauth_browser import ENTRY
from .cli_oauth_client_api import REDEEM, START, CLIOAuthBroker
from .cli_oauth_consent import CALLBACK, CONSENT, FINISHED
from .cli_oauth_flow import Subject, _valid_token
from .oauth_store import OAuthStore
from .oauth_upstream import USER_URL, OAuthUpstreamError, _credential_io

if os.name == "posix":
    import fcntl

_PREFIX = "GC_CLI_BROKER_"
_DB = "cli-oauth.sqlite3"
_LOCK = ".cli-oauth-v1"
_PATHS = frozenset((START, REDEEM, ENTRY, CALLBACK, CONSENT, FINISHED))
_BODY_LIMIT = 65_536
_ID_TIMEOUT = 4.0
_JSON = re.compile(r'application/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?', re.I | re.A)


class ServiceError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid or unavailable CLI OAuth broker configuration.")


def _path(name: str, *, directory: bool = False, private: bool = True) -> Path:
    path = Path(name)
    if not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path:
        raise ServiceError()
    # Verify the chain as well as the leaf. An owner-private directory under a
    # sticky system temp directory is OK; a replaceable path under /tmp is not.
    for ancestor in path.parents:
        info = ancestor.stat()
        if info.st_uid not in (0, os.getuid()) or (
            info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
        ):
            raise ServiceError()
    info = path.stat()
    if (
        info.st_uid != os.getuid()
        or (info.st_mode & (0o077 if private else 0o022))
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
    ):
        raise ServiceError()
    return path


def _secret(path: Path) -> str:
    with path.open("rb") as f:
        data = f.read(4098)
    value = data.removesuffix(b"\n")
    if not 0 < len(value) <= 4096 or not re.fullmatch(rb"[\x21-\x7e]+", value):
        raise ServiceError()
    return value.decode("ascii")


@dataclass(frozen=True)
class Settings:
    origin: str
    port: int
    app_id: str = field(repr=False)
    app_secret: str = field(repr=False)
    key: str = field(repr=False)
    folder: Path
    cert: Path
    tls_key: Path

    @classmethod
    def load(cls, env: Mapping[str, str]) -> Settings:
        try:
            if os.name != "posix":
                raise ServiceError()
            config = {k.removeprefix(_PREFIX): env[k] for k in env if k.startswith(_PREFIX)}
            if (
                set(config)
                != {
                    "ENABLED",
                    "ORIGIN",
                    "APP_ID",
                    "APP_SECRET_FILE",
                    "ENCRYPTION_KEY_FILE",
                    "STATE_DIR",
                    "TLS_CERT_FILE",
                    "TLS_KEY_FILE",
                }
                or config["ENABLED"] != "1"
            ):
                raise ServiceError()
            origin = config["ORIGIN"]
            # Deliberately no public origin, proxy, wildcard, DNS or callback overrides.
            m = re.fullmatch(r"https://127\.0\.0\.1:([1-9][0-9]{0,4})", origin)
            if not m or not 1024 <= (port := int(m[1])) <= 65535:
                raise ServiceError()
            if not re.fullmatch(r"[A-Za-z0-9._~-]{1,256}", config["APP_ID"]):
                raise ServiceError()
            folder = _path(config["STATE_DIR"], directory=True)
            cert = _path(config["TLS_CERT_FILE"], private=False)
            tls = _path(config["TLS_KEY_FILE"])
            app = _path(config["APP_SECRET_FILE"])
            key = _path(config["ENCRYPTION_KEY_FILE"])
            paths = {cert, tls, app, key}
            if len(paths) != 4 or any(p.is_relative_to(folder) for p in paths):
                raise ServiceError()
            credential, encryption = _secret(app), _secret(key)
            Fernet(encryption.encode("ascii"))
            if credential == encryption:
                raise ServiceError()
            return cls(origin, port, config["APP_ID"], credential, encryption, folder, cert, tls)
        except (KeyError, OSError, ValueError, RuntimeError):
            raise ServiceError() from None


def _acquire(settings: Settings):
    # Exclusive process lease; never adopt an existing generic MCP OAuth DB.
    path = settings.folder / _LOCK
    allowed = {_LOCK, _DB, _DB + "-journal"}
    marker = (
        hashlib.sha256((settings.origin + "\0" + settings.app_id).encode()).hexdigest().encode()
    )
    if not path.exists() and any(settings.folder.iterdir()):
        raise ServiceError()
    created = False
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
    except FileExistsError:
        _path(str(path))
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    f = os.fdopen(fd, "r+b")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        names = {p.name for p in settings.folder.iterdir()}
        if names - allowed or (created and names != {_LOCK}):
            raise ServiceError()
        if created:
            f.write(marker)
            f.flush()
            os.fsync(fd)
        elif f.read(65) != marker:
            raise ServiceError()
        return f
    except BaseException:
        f.close()
        raise


def _transport() -> httpx.AsyncBaseTransport:
    # Use the installed HTTPX CA bundle, never ambient proxy, CA file or TLS key-log settings.
    import certifi

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls.load_verify_locations(cafile=certifi.where())
    return httpx.AsyncHTTPTransport(verify=tls, trust_env=False, retries=0)


def _reject(*_):
    raise ValueError


def _unique(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError
    return obj


async def _identity(token: str, transport: httpx.AsyncBaseTransport) -> Subject:
    if not _valid_token(token):
        raise OAuthUpstreamError("invalid_grant")
    flag = _credential_io.set(True)
    try:
        async with (
            asyncio.timeout(_ID_TIMEOUT),
            httpx.AsyncClient(
                transport=transport, follow_redirects=False, trust_env=False, timeout=_ID_TIMEOUT
            ) as cli,
            cli.stream(
                "GET",
                USER_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Authorization": "Bearer " + token,
                },
            ) as response,
        ):
            h = response.headers
            if (
                response.status_code != 200
                or len(h.raw) > 128
                or sum(len(k) + len(v) for k, v in h.raw) > 32768
                or not _JSON.fullmatch(h.get("content-type", ""))
                or h.get("content-encoding", "identity").lower() != "identity"
            ):
                raise ValueError
            length = h.get("content-length")
            if length is not None and (
                not re.fullmatch(r"(?:0|[1-9][0-9]{0,5})", length) or int(length) > _BODY_LIMIT
            ):
                raise ValueError
            body = bytearray()
            async for block in response.aiter_raw():
                if len(block) > _BODY_LIMIT - len(body):
                    raise ValueError
                body.extend(block)
            if length is not None and len(body) != int(length):
                raise ValueError
        obj = json.loads(body.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_reject)
        if type(obj) is not dict or "error" in obj:
            raise ValueError
        subject, login = obj.get("id"), obj.get("login")
        if (
            type(subject) is not str
            or not 0 < len(subject) <= 512
            or not subject.isprintable()
            or any(c.isspace() for c in subject)
            or type(login) is not str
            or login in (".", "..")
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", login)
            or any(
                secret in value
                for secret in (token, quote(token, safe=""))
                for value in (subject, login)
            )
            or any("access_token=" in value.lower() for value in (subject, login))
        ):
            raise ValueError
        return Subject(subject, login)
    except (ValueError, RecursionError, TimeoutError, httpx.HTTPError, httpx.StreamError, OSError):
        raise OAuthUpstreamError("invalid_response") from None
    finally:
        _credential_io.reset(flag)


class Service:
    def __init__(self, settings: Settings) -> None:
        with ExitStack() as stack:
            stack.enter_context(_acquire(settings))
            store = OAuthStore(settings.folder / _DB, settings.key)
            stack.callback(store.close)

            async def verify(token: str) -> Subject:
                return await _identity(token, _transport())

            self.broker = CLIOAuthBroker(
                store,
                broker_origin=settings.origin,
                client_id=settings.app_id,
                client_secret=settings.app_secret,
                verify_identity=verify,
                transport=_transport(),
            )
            self.resources = stack.pop_all()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            try:
                await self.broker.aclose()
            finally:
                self.resources.close()
            await send({"type": "lifespan.shutdown.complete"})
            return
        if scope["type"] != "http":
            raise RuntimeError("HTTP only.")
        if scope.get("path") not in _PATHS:
            await Response(status_code=404, headers={"Cache-Control": "no-store"})(
                scope, receive, send
            )
            return
        await self.broker(scope, receive, send)


def main() -> None:
    # Do not import or instantiate MCP or the native CLI's config/PAT storage.
    try:
        s = Settings.load(os.environ)
        # Check the cert/key before creating a database or acquiring its lease.
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(s.cert), str(s.tls_key), password=lambda: b"")
        app = Service(s)
    except Exception:
        sys.exit("CLI OAuth broker is disabled or its local configuration is invalid.")
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=s.port,
            workers=1,
            interface="asgi3",
            lifespan="on",
            loop="asyncio",
            http="h11",
            ws="none",
            proxy_headers=False,
            forwarded_allow_ips="",
            access_log=False,
            log_config=None,
            log_level="warning",
            server_header=False,
            ssl_certfile=str(s.cert),
            ssl_keyfile=str(s.tls_key),
            limit_concurrency=32,
            backlog=32,
            h11_max_incomplete_event_size=16384,
            timeout_keep_alive=3,
        )
    finally:
        app.resources.close()


if __name__ == "__main__":
    main()
