"""Validated, single-file publication through GitCode's Contents API.

Each call issues exactly one mutation. The public API does not document an
atomic multi-file commit or a branch-head compare-and-swap operation.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Literal
from urllib.parse import quote

from .api import GitCodeAPI, GitCodeError

MAX_FILE_BYTES = 256 * 1024
MAX_ENCODED_FILE_CHARS = 4 * ((MAX_FILE_BYTES + 2) // 3)
MAX_MESSAGE_BYTES = 4096
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
FILE_WRITE_METHODS = {"create_file": "POST", "update_file": "PUT", "delete_file": "DELETE"}


def utf8_bytes(value: str, *, maximum: int) -> bytes:
    """Count encoded bytes without leaking content in validation errors."""
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Use valid UTF-8 text without unpaired surrogates.") from None
    if len(encoded) > maximum:
        raise ValueError("The value exceeds the UTF-8 byte limit.")
    return encoded


def validate_write_branch(value: str) -> str:
    """Require an explicit short branch name, not a ref expression."""
    utf8_bytes(value, maximum=1024)
    if (
        not value
        or value in {"@", "HEAD"}
        or value.startswith(("-", "/", "refs/"))
        or value.endswith(("/", "."))
        or ".." in value
        or "@{" in value
        or any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            or character in "~^:?*[\\%#"
            for character in value
        )
        or any(
            not part or part.startswith(".") or part.endswith(".lock") for part in value.split("/")
        )
    ):
        raise ValueError("Use an explicit short Git branch name, not a tag or ref expression.")
    return value


def validate_commit_message(value: str) -> str:
    utf8_bytes(value, maximum=MAX_MESSAGE_BYTES)
    if not value.strip() or "\x00" in value:
        raise ValueError("Provide a nonblank commit message without NUL characters.")
    return value


def encode_file_content(value: str, encoding: Literal["utf-8", "base64"]) -> str:
    """Produce the canonical Base64 required by the upstream Contents API."""
    if encoding == "utf-8":
        content = utf8_bytes(value, maximum=MAX_FILE_BYTES)
    else:
        if len(value) > MAX_ENCODED_FILE_CHARS:
            raise ValueError("The file exceeds the decoded byte limit.")
        try:
            content = base64.b64decode(value.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError):
            raise ValueError("Use canonical, padded Base64 without whitespace.") from None
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("The file exceeds the decoded byte limit.")
        if base64.b64encode(content).decode("ascii") != value:
            raise ValueError("Use canonical, padded Base64 without whitespace.")
    return base64.b64encode(content).decode("ascii")


def _response_sha(value: Any) -> str | None:
    if isinstance(value, str) and _SHA.fullmatch(value):
        return value.lower()
    return None


def write_file(
    api: GitCodeAPI, prefix: str, action: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Publish one validated file operation and return bounded metadata.

    The documented response examples disagree about whether a commit object is
    present. A missing SHA is a verification requirement, never a reason to repeat
    the mutation or attribute a later branch HEAD to this request.
    """
    payload = dict(arguments)
    path = payload.pop("path")
    if "content" in payload:
        payload["content"] = encode_file_content(payload["content"], payload.pop("encoding"))
    response = api.request(
        FILE_WRITE_METHODS[action], f"{prefix}/contents/{quote(path, safe='/')}", json=payload
    )
    if response is not None and not isinstance(response, dict):
        raise GitCodeError(
            "invalid_response",
            "GitCode returned an unexpected successful response.",
            operation_may_have_completed=True,
        )
    response = response or {}
    commit = response.get("commit")
    content = response.get("content")
    commit_sha = _response_sha(commit.get("sha")) if isinstance(commit, dict) else None
    content_sha = _response_sha(content.get("sha")) if isinstance(content, dict) else None
    result = {
        "operation": action.removesuffix("_file"),
        "status": "accepted",
        "branch": arguments["branch"],
        "path": path,
        "commit_sha": commit_sha,
        "content_sha": content_sha,
        "verification_required": commit_sha is None,
    }
    if commit_sha is None:
        result["note"] = (
            "GitCode accepted the request but did not return a usable commit SHA. "
            "Read the target file and branch before continuing; do not repeat the write "
            "just to obtain a SHA. A later branch HEAD is not proof of this request's commit."
        )
    return {"data": result}
