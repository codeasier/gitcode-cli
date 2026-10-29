"""Credential-free, single-request wrappers for GitCode's Contents API."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..client import GitCodeClient

_BLOB_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _encode_path(value: str, *, allow_root: bool = False) -> str:
    """Encode decoded relative paths; percent sequences are literal filenames."""
    if not isinstance(value, str):
        raise ValueError("Use a decoded UTF-8 relative path.")
    if value == "" and allow_root:
        return ""
    if (
        any(part in {"", ".", ".."} for part in value.split("/"))
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "://" in value
    ):
        raise ValueError("Use a relative path without traversal, empty components or ASCII C0/DEL controls.")
    try:
        return quote(value, safe="/")
    except UnicodeEncodeError:
        raise ValueError("Use valid UTF-8 path text without unpaired surrogates.") from None


def _endpoint(owner: str, repo: str, path: str, *, allow_root: bool = False) -> str:
    encoded_owner = _encode_path(owner)
    encoded_repo = _encode_path(repo)
    if "/" in encoded_owner or "/" in encoded_repo:
        raise ValueError("Owner and repository must each be one path segment.")
    return f"/repos/{encoded_owner}/{encoded_repo}/contents/{_encode_path(path, allow_root=allow_root)}"


def _write_payload(branch: str, message: str) -> dict[str, Any]:
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("Provide an explicit target branch.")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Provide a nonblank commit message.")
    return {"branch": branch, "message": message}


def _content(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Provide already Base64-encoded content as a string.")
    return value


def _blob_sha(value: str) -> str:
    if not isinstance(value, str) or not _BLOB_SHA.fullmatch(value):
        raise ValueError("Provide the expected file Blob SHA as 40 hexadecimal characters.")
    return value


class FileService:
    """Construct Contents requests without choosing transport or entry-point policy.

    Paths are decoded UTF-8 repository-relative strings. Slashes separate path
    components; spaces, Unicode and literal ``?``, ``#`` and ``%`` are encoded
    once. Input is never URL-decoded: the literal filename ``%2F`` becomes
    ``%252F``, not a slash. URL-derived paths must be decoded at the caller's
    boundary. Traversal, empty components, backslashes and ASCII C0/DEL controls
    are rejected; other UTF-8 characters remain filename data.
    Only reads accept an empty path, for the repository root.

    Reads forward query values unchanged, including ``ref`` and ``None``; the
    client owns query encoding/filtering. Writes require an explicit branch and
    message; update/delete additionally require the expected 40-hex Blob SHA.
    The caller must read that Blob SHA from the target branch's file; syntax
    validation cannot prove its object type or current branch state. This is not
    a branch-head compare-and-swap guarantee. Content must already
    be Base64-encoded by the caller; empty content is preserved. Full branch,
    message, content and size policies belong to the entry point, while auth,
    response limits and uncertain-outcome errors belong to the client.

    Each method makes one request and returns its result unchanged. No lookup,
    retry, automatic SHA refresh, success interpretation or content encoding is
    performed here.
    """

    def __init__(self, client: GitCodeClient):
        self.client = client

    def get(self, owner: str, repo: str, path: str, **params: Any) -> Any | None:
        return self.client.get(_endpoint(owner, repo, path, allow_root=True), params=params)

    def create(self, owner: str, repo: str, path: str, *, branch: str, message: str, content: str) -> Any | None:
        payload = _write_payload(branch, message)
        payload["content"] = _content(content)
        return self.client.post(_endpoint(owner, repo, path), json=payload)

    def update(
        self, owner: str, repo: str, path: str, *, branch: str, message: str, content: str, sha: str
    ) -> Any | None:
        payload = _write_payload(branch, message)
        payload.update(content=_content(content), sha=_blob_sha(sha))
        return self.client.put(_endpoint(owner, repo, path), json=payload)

    def delete(self, owner: str, repo: str, path: str, *, branch: str, message: str, sha: str) -> Any | None:
        payload = _write_payload(branch, message)
        payload["sha"] = _blob_sha(sha)
        return self.client.delete(_endpoint(owner, repo, path), json=payload)
