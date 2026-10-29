"""Explicit configuration for the public GitCode OAuth broker."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import AnyHttpUrl, ValidationError

from .config import ConfigurationError

READ_SCOPE = "gitcode:read"
WRITE_SCOPE = "gitcode:write"


def _required(env: Mapping[str, str], name: str, *, secret: bool = False) -> str:
    value = env.get(name, "")
    if (
        not value
        or not value.isascii()
        or len(value) > 4096
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ConfigurationError(f"{name} must be a nonempty value without whitespace.")
    if secret and len(value) < 32:
        raise ConfigurationError(f"{name} must contain at least 32 characters.")
    return value


def https_url(value: str, name: str, *, origin: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and value.isascii()
            and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            and "*" not in value
            and "\\" not in value
            and parsed.port != 0
        )
    except ValueError:
        valid = False
    if not valid or (origin and (parsed.path not in {"", "/"} or parsed.query)):
        suffix = (
            " origin without a path, query or fragment" if origin else " URL without a fragment"
        )
        raise ConfigurationError(f"{name} must be an explicit HTTPS{suffix}.")
    try:
        normalized = str(AnyHttpUrl(value))
    except ValidationError:
        raise ConfigurationError(f"{name} must be a valid HTTPS URL.") from None
    return normalized.rstrip("/") if origin else normalized


@dataclass(frozen=True)
class OAuthSettings:
    public_url: str
    gitcode_client_id: str
    gitcode_client_secret: str = field(repr=False)
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uris: tuple[str, ...]
    encryption_key: str = field(repr=False)
    database: str
    gitcode_scopes: tuple[str, ...] = ()
    allowed_user_ids: tuple[str, ...] = ()

    @property
    def resource_url(self) -> str:
        return self.public_url + "/mcp"

    @property
    def callback_url(self) -> str:
        return self.public_url + "/oauth/gitcode/callback"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> OAuthSettings:
        public_url = https_url(
            _required(env, "GITCODE_MCP_PUBLIC_URL"), "GITCODE_MCP_PUBLIC_URL", origin=True
        )
        redirects = tuple(
            https_url(value.strip(), "GITCODE_MCP_OAUTH_REDIRECT_URIS")
            for value in env.get("GITCODE_MCP_OAUTH_REDIRECT_URIS", "").split(",")
            if value.strip()
        )
        key = _required(env, "GITCODE_MCP_OAUTH_ENCRYPTION_KEY")
        try:
            Fernet(key.encode("ascii"))
        except (ValueError, UnicodeError):
            raise ConfigurationError(
                "GITCODE_MCP_OAUTH_ENCRYPTION_KEY must be a persistent Fernet key."
            ) from None
        database = env.get("GITCODE_MCP_OAUTH_DATABASE", "/var/lib/gitcode-mcp/oauth.sqlite3")
        if not Path(database).is_absolute() or "\x00" in database:
            raise ConfigurationError("GITCODE_MCP_OAUTH_DATABASE must be an absolute file path.")
        scopes = tuple(env.get("GITCODE_OAUTH_SCOPES", "").split())
        if any(not re.fullmatch(r"[A-Za-z0-9_:\-.]+", value) for value in scopes):
            raise ConfigurationError(
                "GITCODE_OAUTH_SCOPES must contain space-separated scope names."
            )
        users = tuple(
            value.strip()
            for value in env.get("GITCODE_MCP_OAUTH_ALLOWED_USER_IDS", "").split(",")
            if value.strip()
        )
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value) for value in users):
            raise ConfigurationError(
                "GITCODE_MCP_OAUTH_ALLOWED_USER_IDS must list stable user IDs."
            )
        upstream_secret = _required(env, "GITCODE_OAUTH_CLIENT_SECRET")
        client_secret = _required(env, "GITCODE_MCP_OAUTH_CLIENT_SECRET", secret=True)
        if client_secret == upstream_secret or key in {client_secret, upstream_secret}:
            raise ConfigurationError(
                "OAuth client secrets and the storage key must be independent."
            )
        return cls(
            public_url=public_url,
            gitcode_client_id=_required(env, "GITCODE_OAUTH_CLIENT_ID"),
            gitcode_client_secret=upstream_secret,
            client_id=_required(env, "GITCODE_MCP_OAUTH_CLIENT_ID"),
            client_secret=client_secret,
            redirect_uris=redirects,
            encryption_key=key,
            database=database,
            gitcode_scopes=scopes,
            allowed_user_ids=users,
        )
