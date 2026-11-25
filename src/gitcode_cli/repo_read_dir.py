"""Read a single non-recursive GitCode Tree page or a verified complete tree object."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from ._redact import redact
from .errors import APIError, GCError
from .repo_read import bounded_json, validate_path, validate_target

DEFAULT_FIELDS = ("name", "path", "gitSHA", "gitType")
JSON_FIELDS = (*DEFAULT_FIELDS, "mode", "modeOctal")
MAX_PAGE = 2**31 - 1
MAX_TREE_PAGES = 10
_SHA1 = re.compile(r"[a-fA-F0-9]{40}")
_MODES = {"040000": "tree", "100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}


@dataclass(frozen=True)
class TreeEntry:
    name: str
    path: str
    mode: str
    kind: str
    sha: str

    def line(self) -> str:
        return f"{self.mode} {self.kind} {self.sha}\t{self.path}"

    def project(self, fields: tuple[str, ...]) -> dict[str, str | int]:
        values: dict[str, str | int] = {
            "name": self.name,
            "path": self.path,
            "gitSHA": self.sha,
            "gitType": self.kind,
            "mode": int(self.mode, 8),
            "modeOctal": self.mode,
        }
        return {field: values[field] for field in fields}


def encode_page(entries: list[TreeEntry], fields: tuple[str, ...] | None, token: str) -> bytes:
    if fields is None:
        return "".join(f"{entry.line()}\n" for entry in entries).encode("utf-8")
    text = json.dumps([entry.project(fields) for entry in entries], ensure_ascii=False) + "\n"
    if redact(text, token) != text:
        raise APIError("Refusing to display the active GitCode token.")
    return text.encode("utf-8")


def _entry(row: object, directory: str | None, token: str) -> TreeEntry:
    if not isinstance(row, dict):
        raise APIError("Invalid Tree entry.")
    name, path = row.get("name"), row.get("path")
    if (
        not isinstance(name, str)
        or not name
        or not name.isprintable()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or not isinstance(path, str)
        or path != (f"{directory}/{name}" if directory is not None else name)
        or len(path) > 4096
    ):
        raise APIError("Tree response did not confirm a safe immediate child of the requested directory.")
    mode, kind, sha = row.get("mode"), row.get("type"), row.get("sha")
    if (
        not isinstance(mode, str)
        or mode not in _MODES
        or not isinstance(kind, str)
        or kind != _MODES[mode]
        or not isinstance(sha, str)
        or not _SHA1.fullmatch(sha)
    ):
        raise APIError("Tree entry did not confirm a Git object type, mode and SHA.")
    entry = TreeEntry(name, path, mode, kind, sha)
    line = entry.line()
    if redact(line, token) != line:
        raise APIError("Refusing to display the active GitCode token.")
    return entry


def fetch_page(
    owner: str, repo: str, path: str | None, ref: str, page: int, per_page: int, token: str
) -> list[TreeEntry]:
    if type(page) is not int or not 1 <= page <= MAX_PAGE or type(per_page) is not int or not 1 <= per_page <= 100:
        raise GCError("Use a positive 32-bit page number and a page size from 1 through 100.")
    validate_target(owner, repo, ref)
    params = {"page": str(page), "per_page": str(per_page)}
    if path is not None:
        validate_path(path)
        params["file_path"] = path
    endpoint = f"/repos/{owner}/{repo}/git/trees/{quote(ref, safe='')}"
    result = bounded_json("Tree", endpoint, params, token, (owner, repo, ref, *params.values()))
    if not isinstance(result, dict) or not isinstance(result.get("tree"), list):
        raise APIError("Expected a Tree response containing a list.")
    if result.get("truncated", False) is not False or len(result["tree"]) > per_page:
        raise APIError("Tree response was truncated or exceeded the requested page size.")
    entries: dict[str, TreeEntry] = {}
    for row in result["tree"]:
        entry = _entry(row, path, token)
        if entry.name in entries:
            raise APIError("Tree response contains a duplicate directory entry.")
        entries[entry.name] = entry
    return list(entries.values())


def _git_tree_oid(entries: list[TreeEntry]) -> str:
    # Git sorts a directory as if its name ended in '/', and writes the mode
    # without leading zeroes. Hash the canonical order; do not reorder stdout.
    parts: list[tuple[bytes, bytes]] = []
    for entry in entries:
        name = entry.name.encode("utf-8")
        key = name + (b"/" if entry.kind == "tree" else b"")
        record = entry.mode.lstrip("0").encode("ascii") + b" " + name + b"\0" + bytes.fromhex(entry.sha)
        parts.append((key, record))
    size = sum(len(record) for _, record in parts)
    digest = hashlib.sha1(f"tree {size}\0".encode("ascii"), usedforsecurity=False)
    for _, record in sorted(parts):
        digest.update(record)
    return digest.hexdigest()


def fetch_verified_tree(owner: str, repo: str, tree_sha: str, per_page: int, token: str) -> list[TreeEntry]:
    if not _SHA1.fullmatch(tree_sha):
        raise GCError("--all requires a full 40-hex Git tree SHA for --ref, not a branch, tag or commit.")
    rows: list[TreeEntry] = []
    names: set[str] = set()
    for page in range(1, MAX_TREE_PAGES + 1):
        chunk = fetch_page(owner, repo, None, tree_sha, page, per_page, token)
        for entry in chunk:
            if entry.name in names:
                raise APIError("Tree pages contain a repeated directory entry; refusing an incomplete listing.")
            names.add(entry.name)
        rows.extend(chunk)
        if len(chunk) < per_page:
            break
    if _git_tree_oid(rows) != tree_sha.lower():
        if len(rows) == MAX_TREE_PAGES * per_page:
            raise APIError("Tree page limit reached without verifying the complete tree. Use manual pages instead.")
        raise APIError("Directory entries do not match the requested tree SHA. Use a tree object, not a commit.")
    return rows
