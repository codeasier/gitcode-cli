"""Read one GitCode Contents blob without buffering an unbounded response or following download links."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import unicodedata
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

import click

from ._redact import redact
from .errors import APIError, GCError
from .release_files import directory, save_verified
from .repo_read import MAX_RESPONSE, bounded_json, origin_target, validate_path, validate_target
from .services.files import contents_path

__all__ = [
    "JSON_FIELDS",
    "MAX_FILE",
    "MAX_RESPONSE",
    "METADATA_FIELDS",
    "encode_file",
    "fetch_file",
    "origin_target",
    "write_file",
    "write_stdout",
]

MAX_FILE = 1024 * 1024
METADATA_FIELDS = ("name", "path", "gitSHA", "size", "type", "encoding")
JSON_FIELDS = (*METADATA_FIELDS, "content")


def _blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw, usedforsecurity=False).hexdigest()


def _decode(row: Any, path: str) -> bytes:
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
    if row.get("sha") != _blob_sha(raw):
        raise APIError("File bytes do not match the Git blob SHA in the Contents response.")
    return raw


def fetch_file(owner: str, repo: str, path: str, ref: str | None, token: str) -> bytes:
    validate_target(owner, repo, ref)
    validate_path(path)
    params = {"ref": ref} if ref is not None else {}
    row = bounded_json("Contents", contents_path(owner, repo, path), params, token, (owner, repo, path, ref or ""))
    return _decode(row, path)


def encode_file(path: str, raw: bytes, fields: tuple[str, ...], token: str) -> bytes:
    """Project only the verified path and inline blob, never response URLs or extra fields."""
    values: dict[str, str | int] = {
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "size": len(raw),
        "type": "file",
        "encoding": "base64",
    }
    if "gitSHA" in fields:
        values["gitSHA"] = _blob_sha(raw)
    if "content" in fields:
        if token and (token.encode("ascii") in raw or quote(token, safe="").encode("ascii") in raw):
            raise APIError("Refusing to display the active GitCode token.")
        values["content"] = base64.b64encode(raw).decode("ascii")
    text = json.dumps({field: values[field] for field in fields}, ensure_ascii=False) + "\n"
    if redact(text, token) != text:
        raise APIError("Refusing to display the active GitCode token.")
    return text.encode("utf-8")


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
