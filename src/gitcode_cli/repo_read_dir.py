"""List immediate entries in exactly one non-recursive GitCode Tree API page."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from ._redact import redact
from .errors import APIError, GCError
from .repo_read import bounded_json, validate_path, validate_target

JSON_FIELDS = ("name", "path", "gitSHA", "gitType")
MAX_PAGE = 2**31 - 1
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

    def project(self, fields: tuple[str, ...]) -> dict[str, str]:
        values = {"name": self.name, "path": self.path, "gitSHA": self.sha, "gitType": self.kind}
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
        or not re.fullmatch(r"[a-fA-F0-9]{40}", sha)
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
