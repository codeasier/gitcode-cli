"""Read (never parse or execute) a public workflow registration's file at an explicitly supplied commit."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote_to_bytes

from .errors import APIError, GCError
from .repo_read import bounded_json_response, validate_target
from .repo_read_dir import MAX_TREE_PAGES, TreeEntry, fetch_page, fetch_verified_tree
from .repo_read_file import fetch_file, write_stdout

_COMMIT = re.compile(r"[A-Fa-f0-9]{40}")
_PATH = re.compile(r"\.gitcode/workflows/([a-zA-Z0-9_][a-zA-Z0-9_.-]{0,249}\.ya?ml)")


def _guard_secret(raw: bytes, token: str) -> None:
    # Check literal, mixed-case/partial percent encoding and nested encoding without unbounded decoding.
    if not token:
        return
    secret = token.encode("ascii")
    for _ in range(3):
        if secret in raw:
            raise APIError("Refusing to transmit or display the active GitCode token.")
        decoded = unquote_to_bytes(raw)
        if decoded == raw:
            return
        raw = decoded
    if secret in raw or unquote_to_bytes(raw) != raw:
        raise APIError("Cannot safely display or transmit nested URL-encoded data.")


def yaml_target(local: str | None, global_repo: str | None, ref: str, token: str) -> tuple[str, str, str]:
    if local is not None and global_repo is not None and local != global_repo:
        raise GCError("Conflicting explicit repository targets for workflow YAML.")
    repo = local if local is not None else global_repo
    if repo is None or repo.count("/") != 1:
        raise GCError("Workflow YAML requires explicit -R OWNER/REPO.")
    owner, name = repo.split("/")
    if not _COMMIT.fullmatch(ref) or ref == "0" * 40:
        raise GCError("Workflow YAML requires a full nonzero SHA-1 commit, not a branch, tag or default ref.")
    validate_target(owner, name, ref)
    if token and (not token.isascii() or not token.isprintable() or any(c.isspace() for c in token)):
        raise APIError("Invalid GitCode authentication token.")
    # Anonymous registration must not send a credential embedded in an explicit repository argument either.
    _guard_secret(f"{owner}/{name}/{ref}/{ref.lower()}".encode("ascii"), token)
    return owner, name, ref.lower()


def _entry(rows: list[TreeEntry], name: str, modes: set[str]) -> TreeEntry:
    matches = [row for row in rows if row.name == name]
    if len(matches) != 1 or matches[0].mode not in modes or matches[0].sha == "0" * 40:
        raise APIError("Tree did not confirm the expected unique directory or regular workflow file.")
    return matches[0]


def _root_at_commit(owner: str, repo: str, commit: str, token: str) -> list[TreeEntry]:
    # The commit detail contract identifies the commit, not its root tree OID. The Tree endpoint
    # resolves the exact same ref; never compare a commit OID with the hash of its root tree.
    data, _, _ = bounded_json_response(
        "Commit detail", f"/repos/{owner}/{repo}/commits/{commit}", {}, token, (owner, repo, commit), strict_json=True
    )
    if not isinstance(data, dict) or data.get("sha") != commit:
        raise APIError("Commit detail did not confirm the requested SHA-1.")
    names: set[str] = set()
    rows: list[TreeEntry] = []
    for page in range(1, MAX_TREE_PAGES + 1):
        chunk = fetch_page(owner, repo, None, commit, page, 100, token)
        for entry in chunk:
            if entry.name in names:
                raise APIError("Repeated root tree entry; cannot verify the registered workflow path.")
            names.add(entry.name)
        rows.extend(chunk)
        if len(chunk) < 100:
            return rows
    raise APIError("Cannot establish a complete root tree inside the page limit.")


def read_workflow_yaml(owner: str, repo: str, commit: str, path: str, token: str) -> None:
    match = _PATH.fullmatch(path)
    if not match:
        raise APIError("Expected a registered .gitcode/workflows/<filename>.yml or .yaml path.")
    _guard_secret(path.encode("ascii"), token)
    dotdir = _entry(_root_at_commit(owner, repo, commit, token), ".gitcode", {"040000"})
    workflows = _entry(fetch_verified_tree(owner, repo, dotdir.sha, 100, token), "workflows", {"040000"})
    file = _entry(fetch_verified_tree(owner, repo, workflows.sha, 100, token), match[1], {"100644", "100755"})
    raw = fetch_file(owner, repo, path, commit, token)
    if hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw, usedforsecurity=False).hexdigest() != file.sha.lower():
        raise APIError("Workflow file bytes do not match the pinned tree entry.")
    _guard_secret(raw, token)
    try:
        write_stdout(raw)
    except GCError:
        raise GCError("Workflow YAML must be UTF-8 text without unsafe control characters.") from None
