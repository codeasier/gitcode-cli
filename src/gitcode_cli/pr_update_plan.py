"""Compare immutable commits from a verified, same-repository PR snapshot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .errors import APIError, GCError
from .repo import is_single_ref
from .repo_read import bounded_json, validate_target

MAX_PR_NUMBER = 2**31 - 1
OidRelationship = Literal["same-commit", "head-includes-base", "head-is-ancestor-of-base", "diverged"]


@dataclass(frozen=True)
class _PRRef:
    ref: str
    oid: str
    repository_id: int | None
    namespace_id: int | None


@dataclass(frozen=True)
class _PRSnapshot:
    id: int
    head: _PRRef
    base: _PRRef


@dataclass(frozen=True)
class PRUpdatePlan:
    snapshot: _PRSnapshot
    merge_base_oid: str
    relationship: OidRelationship


def _oid(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value) or value == "0" * 40:
        raise APIError("PR update plan requires full, nonzero commit SHAs.")
    return value.lower()


def _optional_id(resource: dict) -> int | None:
    if "id" not in resource:
        return None
    value = resource["id"]
    if type(value) is not int or value <= 0:
        raise APIError("PR update plan received an invalid repository or namespace ID.")
    return value


def _api_urls(path: str) -> tuple[str, str]:
    return f"https://api.gitcode.com/api/v5{path}", f"https://gitcode.com/api/v5{path}"


def _read_side(side: object, owner: str, repo: str) -> _PRRef:
    if not isinstance(side, dict):
        raise APIError("PR update plan requires both the head and base metadata.")
    source = side.get("repo")
    target = f"{owner}/{repo}"
    if not isinstance(source, dict) or source.get("full_name") != target:
        raise APIError("PR update plan requires both sides to identify the exact same selected repository.")
    if (
        source.get("path", repo) != repo
        or any(source.get(key, target) != target for key in ("full_path", "path_with_namespace"))
        or ("url" in source and source["url"] not in _api_urls(f"/repos/{target}"))
        or (
            "html_url" in source
            and source["html_url"] not in (f"https://gitcode.com/{target}", f"https://gitcode.com/{target}/")
        )
    ):
        raise APIError("PR update plan received contradictory repository identity.")
    namespace_id = None
    if "namespace" in source:
        namespace = source["namespace"]
        path_fields = ("path", "full_path")
        # GitCode's namespace full_name can be a display name. Only path and
        # full_path are namespace paths; neither may override the other.
        if (
            not isinstance(namespace, dict)
            or not any(key in namespace for key in path_fields)
            or any(namespace.get(key, owner) != owner for key in path_fields)
            or (
                "html_url" in namespace
                and namespace["html_url"] not in (f"https://gitcode.com/{owner}", f"https://gitcode.com/{owner}/")
            )
        ):
            raise APIError("PR update plan received missing or contradictory namespace identity.")
        namespace_id = _optional_id(namespace)
    branch = side.get("ref")
    if not isinstance(branch, str) or branch in {"HEAD", "@"} or len(branch) > 1024 or not is_single_ref(branch):
        raise APIError("PR update plan requires literal head and base branch names.")
    return _PRRef(branch, _oid(side.get("sha")), _optional_id(source), namespace_id)


def _read_snapshot(owner: str, repo: str, number: int, token: str) -> _PRSnapshot:
    path = f"/repos/{owner}/{repo}/pulls/{number}"
    item = bounded_json("PR detail", path, {}, token, (owner, repo, str(number)))
    if (
        not isinstance(item, dict)
        or type(item.get("number")) is not int
        or item["number"] != number
        or type(item.get("id")) is not int
        or item["id"] <= 0
        or item.get("state") != "open"
    ):
        raise APIError("PR update plan requires a verified open pull request.")
    if ("url" in item and item["url"] not in _api_urls(path)) or (
        "html_url" in item
        and item["html_url"]
        not in tuple(
            f"https://gitcode.com/{owner}/{repo}/{kind}/{number}{end}"
            for kind in ("pull", "pulls", "merge_requests")
            for end in ("", "/")
        )
    ):
        raise APIError("PR update plan received a contradictory PR identity.")
    head = _read_side(item.get("head"), owner, repo)
    base = _read_side(item.get("base"), owner, repo)
    for head_id, base_id in ((head.repository_id, base.repository_id), (head.namespace_id, base.namespace_id)):
        if head_id is not None and base_id is not None and head_id != base_id:
            raise APIError("PR update plan received contradictory repository or namespace IDs.")
    if head.ref == base.ref:
        raise APIError("PR update plan requires distinct head and base branches.")
    return _PRSnapshot(item["id"], head, base)


def _compare(owner: str, repo: str, start: str, end: str, token: str) -> str:
    comparison = bounded_json(
        "Commit comparison", f"/repos/{owner}/{repo}/compare/{start}...{end}", {}, token, (owner, repo, start, end)
    )
    if (
        not isinstance(comparison, dict)
        or type(comparison.get("truncated")) is not int
        or comparison["truncated"] != 0
        or not isinstance(comparison.get("commits"), list)
        or not isinstance(comparison.get("files"), list)
    ):
        raise APIError("Commit comparison is missing, malformed or truncated; PR update plan unavailable.")
    base = comparison.get("base_commit")
    merge_base = comparison.get("merge_base_commit")
    if not isinstance(base, dict) or _oid(base.get("sha")) != start or not isinstance(merge_base, dict):
        raise APIError("Commit comparison did not confirm the start SHA and merge base.")
    return _oid(merge_base.get("sha"))


def build_update_plan(owner: str, repo: str, number: int, token: str) -> PRUpdatePlan:
    """Use at most four bounded GETs, never mutable branch names in comparisons."""
    validate_target(owner, repo, None)
    if type(number) is not int or not 1 <= number <= MAX_PR_NUMBER:
        raise GCError("Provide a positive 32-bit pull request number.")
    snapshot = _read_snapshot(owner, repo, number, token)
    head, base = snapshot.head.oid, snapshot.base.oid
    relationship: OidRelationship
    if head == base:
        merge_base, relationship = base, "same-commit"
    else:
        # The documented response echoes only the starting commit. Compare in
        # both directions to check both start SHAs and one agreed merge base.
        merge_base = _compare(owner, repo, base, head, token)
        if _compare(owner, repo, head, base, token) != merge_base:
            raise APIError("Commit comparisons disagree on their merge base; PR update plan unavailable.")
        if merge_base == base:
            relationship = "head-includes-base"
        elif merge_base == head:
            relationship = "head-is-ancestor-of-base"
        else:
            relationship = "diverged"
    if _read_snapshot(owner, repo, number, token) != snapshot:
        raise APIError("PR identity, refs or SHAs changed during the comparison; run the plan again.")
    return PRUpdatePlan(snapshot, merge_base, relationship)
