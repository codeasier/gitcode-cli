"""Read one GitCode Contents blob without buffering an unbounded response or following download links."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, BinaryIO

import click
import httpx

from ._redact import redacted_transport
from .client import BASE_URL
from .errors import APIError, GCError, NetworkError
from .release_files import directory, save_verified
from .repo import is_single_ref
from .services.files import contents_path
from .transport import ResponseTooLargeError, read_response_bytes

MAX_FILE = 1024 * 1024
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
            target = origin[len(prefix) :].removesuffix(".git")
            if target.count("/") == 1:
                return target
    raise GCError("Cannot identify an exact GitCode origin; use -R OWNER/REPO.")


def _target(owner: str, repo: str, path: str, ref: str | None) -> str:
    if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}", name) for name in (owner, repo)):
        raise GCError("Expected literal GitCode owner and repository names.")
    if not path or len(path) > 4096 or not path.isprintable() or re.match(r"^[a-zA-Z]:", path):
        raise GCError("Expected a printable, repository-relative file path.")
    if ref is not None and (not is_single_ref(ref) or ref == "@" or len(ref) > 1024):
        raise GCError("Expected a single literal branch, tag, or commit for --ref.")
    try:
        return BASE_URL.rstrip("/") + contents_path(owner, repo, path)
    except ValueError as exc:
        raise GCError(str(exc)) from None


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def _decode(blob: bytes, path: str) -> bytes:
    try:
        row = json.loads(blob, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise APIError("Invalid Contents JSON response.") from None
    if not isinstance(row, dict) or row.get("type") != "file":
        raise APIError("Expected one regular file in the Contents response.")
    if row.get("path") != path or row.get("name") != path.rsplit("/", 1)[-1] or row.get("encoding") != "base64":
        raise APIError("Contents response did not confirm the requested path and Base64 encoding.")
    size, content = row.get("size"), row.get("content")
    if type(size) is not int or not 0 <= size <= MAX_FILE:
        raise APIError("Invalid file size or file exceeds the 1 MiB limit.")
    expected = 4 * ((size + 2) // 3)
    if not isinstance(content, str) or len(content) != expected:
        raise APIError("Contents Base64 length does not match the reported size.")
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        raise APIError("Invalid Base64 file content.") from None
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != content:
        raise APIError("Contents response contained invalid Base64 or the wrong number of bytes.")
    sha = hashlib.sha1(f"blob {size}\0".encode("ascii") + raw, usedforsecurity=False).hexdigest()
    if row.get("sha") != sha:
        raise APIError("File bytes do not match the Git blob SHA in the Contents response.")
    return raw


def fetch_file(owner: str, repo: str, path: str, ref: str | None, token: str) -> bytes:
    url = _target(owner, repo, path, ref)
    params = {"ref": ref} if ref is not None else {}
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if token:
        if not token.isascii() or not token.isprintable() or any(c.isspace() for c in token):
            raise APIError("Invalid GitCode authentication token.")
        if any(token in value for value in (owner, repo, path, ref or "")):
            raise APIError("Refusing to send the active GitCode token outside the authorization header.")
        headers["Authorization"] = f"Bearer {token}"
    try:
        with (
            httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client,
            redacted_transport(token),
            client.stream("GET", url, params=params, headers=headers) as response,
        ):
            if response.status_code != 200:
                raise APIError(f"GitCode Contents API returned HTTP {response.status_code}.", response.status_code)
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise APIError("Refusing a compressed Contents response.")
            body = read_response_bytes(response, max_response_bytes=MAX_RESPONSE)
    except ResponseTooLargeError:
        raise APIError("Contents response exceeds the 2 MiB limit.") from None
    except httpx.HTTPError:
        raise NetworkError("Could not read the file from GitCode.") from None
    return _decode(body, path)


def write_stdout(raw: bytes) -> None:
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise GCError("Binary content: use --output to save a new file.") from None
    if any(c not in "\t\n" and unicodedata.category(c) in {"Cc", "Cf"} for c in text):
        raise GCError("Unsafe control characters: use --output to save a new file.")
    click.open_file("-", "wb").write(raw)


def write_file(path: Path, raw: bytes) -> None:
    def write(stream: BinaryIO) -> None:
        if stream.write(raw) != len(raw):
            raise OSError("Incomplete local write.")
        stream.flush()
        os.fsync(stream.fileno())

    # Use no-follow parents and publish a complete file atomically via link.
    # An existing destination, including one that races publication, is untouched.
    try:
        with directory(path.parent, writable=True) as parent:
            save_verified(path.parent, parent, path.name, write)
    except FileExistsError:
        raise GCError("Output already exists; choose a new file.") from None
    except (OSError, GCError):
        raise GCError("Cannot save output; use a new file in a trusted POSIX directory without symlinks.") from None
