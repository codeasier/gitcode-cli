"""Common policy for bounded reads of GitCode repository resources."""

from __future__ import annotations

import json
import re
import subprocess
from contextlib import closing, nullcontext
from typing import Any, Literal

import httpx

from ._redact import redact, redacted_transport
from .client import BASE_URL
from .errors import APIError, GCError, NetworkError
from .repo import is_single_ref
from .transport import ResponseTooLargeError, read_response_bytes

MAX_RESPONSE = 2 * 1024 * 1024


def origin_target(origin: str) -> str:
    # The common remote parser drops ports and userinfo. Only infer a target
    # from canonical GitCode spellings; ambiguous origins require explicit -R.
    prefixes = (
        "https://gitcode.com/",
        "git@gitcode.com:",
        "ssh://git@gitcode.com/",
        "git@ssh.gitcode.com:",
        "ssh://git@ssh.gitcode.com/",
        "ssh://git@ssh.gitcode.com:443/",
    )
    for prefix in prefixes:
        if origin.startswith(prefix):
            target = origin[len(prefix) :].removesuffix("/").removesuffix(".git")
            if target.count("/") == 1:
                return target
    raise GCError("Cannot identify an exact GitCode origin; use -R OWNER/REPO.")


def resolve_origin_target() -> str:
    error = "Cannot identify an exact GitCode origin; use -R OWNER/REPO."
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "--all", "--", "origin"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        raise GCError(error) from None
    urls = result.stdout.splitlines()
    if len(urls) != 1:
        raise GCError(error)
    return origin_target(urls[0])


def validate_target(owner: str, repo: str, ref: str | None) -> None:
    if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}", name) for name in (owner, repo)):
        raise GCError("Expected literal GitCode owner and repository names.")
    if ref is not None and (not is_single_ref(ref) or ref == "@" or len(ref) > 1024):
        raise GCError("Expected a single literal reference for --ref.")


def validate_path(path: str) -> None:
    if (
        not path.isprintable()
        or len(path) > 4096
        or re.match(r"^[a-zA-Z]:", path)
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or "\\" in path
        or "://" in path
    ):
        raise GCError("Expected a printable, repository-relative path without traversal or empty components.")


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def bounded_json(
    resource: Literal[
        "Contents",
        "Tree",
        "Issue status",
        "Issue comments",
        "fork sync status",
        "PR detail",
        "Commit comparison",
        "Release metadata",
    ],
    endpoint: str,
    params: dict[str, str],
    token: str,
    target_parts: tuple[str, ...],
) -> Any:
    return bounded_json_response(resource, endpoint, params, token, target_parts)[0]


def bounded_read_url(endpoint: str, params: dict[str, str]) -> httpx.URL:
    return httpx.URL(BASE_URL.rstrip("/") + endpoint, params=params)


def bounded_json_response(
    resource: Literal[
        "Contents",
        "Tree",
        "Issue status",
        "Issue comments",
        "fork sync status",
        "PR detail",
        "Commit comparison",
        "Release metadata",
    ],
    endpoint: str,
    params: dict[str, str],
    token: str,
    target_parts: tuple[str, ...],
    *,
    client: httpx.Client | None = None,
) -> tuple[Any, httpx.Headers, httpx.URL]:
    # Endpoints are built locally from validated components. Never follow
    # URLs obtained from a response, redirect, environment or caller option.
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if token:
        if not token.isascii() or not token.isprintable() or any(c.isspace() for c in token):
            raise APIError("Invalid GitCode authentication token.")
        if any(redact(value, token) != value for value in target_parts):
            raise APIError("Refusing to send the active GitCode token outside the authorization header.")
        headers["Authorization"] = f"Bearer {token}"
    request = httpx.Request("GET", bounded_read_url(endpoint, params), headers=headers)
    try:
        with (
            nullcontext(client)
            if client is not None
            else httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as active,
            redacted_transport(token),
            closing(active.send(request, auth=None, follow_redirects=False, stream=True)) as response,
        ):
            if response.status_code != 200:
                raise APIError(f"GitCode {resource} API returned HTTP {response.status_code}.", response.status_code)
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise APIError(f"Refusing a compressed {resource} response.")
            body = read_response_bytes(response, max_response_bytes=MAX_RESPONSE)
    except ResponseTooLargeError:
        raise APIError(f"{resource} response exceeds the 2 MiB limit.") from None
    except (httpx.HTTPError, httpx.StreamError):
        raise NetworkError(f"Could not read the GitCode {resource} response.") from None
    try:
        value = json.loads(body, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise APIError(f"Invalid {resource} JSON response.") from None
    return value, response.headers, request.url
