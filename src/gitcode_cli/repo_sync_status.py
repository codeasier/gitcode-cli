"""Read GitCode's fork sync status, not its separate PUT synchronization operation."""

from __future__ import annotations

import json
import re

from ._redact import redact
from .errors import APIError, GCError
from .repo import is_single_ref
from .repo_read import bounded_json, validate_target

# A provider message is untrusted display text, not a log or a link to follow.
_SENSITIVE = re.compile(
    r"://|[=@%]|\b(?:bearer|basic|authorization|cookie|token|password|secret|credential|signature|api[-_ ]?key)\b"
    r"|(?:access|private|refresh|id|session)[-_]?token|-----BEGIN |\b(?:gh[pousr]_|github_pat_|glpat-)",
    re.IGNORECASE,
)


def read_sync_status(repository: str, branch: str, token: str) -> str:
    owner, _, repo = repository.partition("/")
    validate_target(owner, repo, None)
    if not is_single_ref(branch) or branch in {"@", "HEAD"} or branch.startswith("refs/") or len(branch) > 1024:
        raise GCError("Expected a single literal branch name for --branch.")
    if not token:
        raise GCError("GitCode fork sync status requires authentication. Run 'gc auth login'.")
    result = bounded_json(
        "fork sync status", f"/repos/{owner}/{repo}/sync_repo", {"branch": branch}, token, (owner, repo, branch)
    )
    if not isinstance(result, dict) or type(result.get("repo_sync_result")) is not bool:
        raise APIError("Invalid GitCode fork sync status: expected a boolean repo_sync_result.")
    message = result.get("repo_sync_message")
    if not isinstance(message, str):
        raise APIError("Invalid GitCode fork sync status: expected a string repo_sync_message.")
    if (
        len(message) > 512
        or not message.isprintable()
        or redact(message, token) != message
        or _SENSITIVE.search(message)
    ):
        message = "[message withheld]"
    return json.dumps(
        {"repo_sync_result": result["repo_sync_result"], "repo_sync_message": message}, ensure_ascii=False
    )
