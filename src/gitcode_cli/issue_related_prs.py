"""GitCode-native associations observed in one issue-scoped response, not closing PRs."""

from __future__ import annotations

import json
import re

import httpx

from ._redact import redact
from .config import Accounts, load_config
from .errors import APIError, ConfigError, GCError
from .repo_read import bounded_json_response, validate_target

_MAX_ROWS = 100
_MAX_ID_EXCLUSIVE = 10**20
_BAD_ID = "Cannot verify the GitCode related pull request identity."
_PARTIAL = "Incomplete or contradictory GitCode related pull request response; no partial result was printed."
_WEB = r"https://(?:gitcode|(?:api\.)?atomgit)\.com"


def _check_headers(headers: httpx.Headers, count: int) -> None:
    # This endpoint does not define pages. Never follow a provider-supplied URL or
    # assume that a bound, or the absence of these headers, proves completeness.
    if any(key in headers for key in ("link", "content-range")):
        raise APIError(_PARTIAL)
    acceptable = {
        "x-total": (str(count),),
        "x-total-count": (str(count),),
        "x-total-pages": ("1",) if count else ("0", "1"),
        "x-page": ("1",),
        "x-next-page": ("",),
        "x-prev-page": ("",),
        "x-truncated": ("0", "false"),
        "x-incomplete-results": ("0", "false"),
        "x-has-more": ("0", "false"),
        "x-has-next-page": ("0", "false"),
    }
    for key, expected in acceptable.items():
        values = headers.get_list(key)
        if values and (len(values) != 1 or values[0].strip().lower() not in expected):
            raise APIError(_PARTIAL)
    size = headers.get_list("x-per-page")
    if size and (len(size) != 1 or not re.fullmatch(r"[1-9][0-9]{0,9}", size[0]) or int(size[0]) < count):
        raise APIError(_PARTIAL)


def _matches(value: object, pattern: str) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value, flags=re.ASCII) is not None


def _if_present(row: dict, pattern: str, *keys: str) -> None:
    if any(key in row and not _matches(row[key], pattern) for key in keys):
        raise APIError(_BAD_ID)


def _numeric_id(value: object) -> int:
    if type(value) is not int or not 0 < value < _MAX_ID_EXCLUSIVE:
        raise APIError(_BAD_ID)
    return value


def _base_project_id(row: dict, repo: dict) -> int | None:
    explicit = _numeric_id(repo["id"]) if "id" in repo else None
    target = _numeric_id(row["target_project_id"]) if "target_project_id" in row else None
    if explicit is not None and target is not None and explicit != target:
        raise APIError(_BAD_ID)
    proven = explicit if explicit is not None else target
    # An unqualified project ID is not enough to decide whether it denotes the
    # head or base. Accept it only when an explicit base/target claim confirms it.
    if "project_id" in row and _numeric_id(row["project_id"]) != proven:
        raise APIError(_BAD_ID)
    return proven


def _identity(row: object, owner: str, repo: str) -> tuple[int, int, str, int | None]:
    if not isinstance(row, dict):
        raise APIError(_BAD_ID)
    pr_id, number = _numeric_id(row.get("id")), _numeric_id(row.get("number"))
    if "iid" in row and _numeric_id(row["iid"]) != number:
        raise APIError(_BAD_ID)

    base = row.get("base")
    source = base.get("repo") if isinstance(base, dict) else None
    owner_pattern = f"(?i:{re.escape(owner)})"  # Only the ASCII namespace permits case aliases, not the repo slug.
    target = f"{owner_pattern}/{re.escape(repo)}"
    if not isinstance(source, dict) or not _matches(source.get("full_name"), target):
        raise APIError(_BAD_ID)
    _if_present(source, re.escape(repo), "path")
    _if_present(source, target, "full_path", "path_with_namespace")
    _if_present(source, rf"{_WEB}/{target}(?:/|\.git)?", "html_url")
    api_repo = rf"https://(?:api\.)?gitcode\.com/api/v5/repos/{target}"
    _if_present(source, api_repo, "url")
    if "namespace" in source:
        namespace = source["namespace"]
        if not isinstance(namespace, dict):
            raise APIError(_BAD_ID)
        _if_present(namespace, owner_pattern, "path", "full_path")
        _if_present(namespace, rf"{_WEB}/{owner_pattern}/?", "html_url")
    pr_web = rf"{_WEB}/{target}/(?:merge_requests|pulls|pull)/{number}"
    if not _matches(row.get("html_url"), pr_web + "/?"):
        raise APIError(_BAD_ID)
    _if_present(row, rf"{api_repo}/pulls/{number}", "url")
    _if_present(row, pr_web + "/diffs/?", "diff_url")
    return pr_id, number, source["full_name"], _base_project_id(row, source)


def read_related_prs(target: str | None, issue: str, token: str) -> str:
    if target is None:
        raise GCError("Select the issue repository explicitly with -R OWNER/REPO.")
    owner, _, repo = target.partition("/")
    validate_target(owner, repo, None)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", issue):
        raise GCError("Expected a literal positive issue number.")
    if not token:
        # The root group treats a failed PAT lookup like a missing token for its
        # optional-auth commands. A broken/inactive account is not a logged-out user.
        try:
            saved_accounts = Accounts.from_config(load_config()).tokens
        except (ConfigError, OSError):
            raise GCError("Cannot resolve configured GitCode credentials; anonymous fallback refused.") from None
        if saved_accounts:
            raise GCError("Select an active saved GitCode account; anonymous fallback refused.")
    endpoint = f"/repos/{target}/issues/{issue}/pull_requests"
    rows, headers, _ = bounded_json_response("PR detail", endpoint, {}, token, (endpoint,), strict_json=True)
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise APIError(_PARTIAL)
    _check_headers(headers, len(rows))
    ids: set[int] = set()
    numbers: set[int] = set()
    result: list[dict] = []
    base_id: int | None = None
    for row in rows:
        pr_id, number, canonical, row_base_id = _identity(row, owner, repo)
        if pr_id in ids or number in numbers:
            raise APIError(_BAD_ID)
        # Every row names the same selected base repository, including when it
        # has an ASCII case alias. An omitted ID cannot clear an earlier claim.
        if row_base_id is not None:
            if base_id is not None and row_base_id != base_id:
                raise APIError(_BAD_ID)
            base_id = row_base_id
        ids.add(pr_id)
        numbers.add(number)
        result.append({"id": pr_id, "number": number, "repository": canonical})
    rendered = json.dumps(result, ensure_ascii=True)
    if redact(rendered, token) != rendered:
        raise APIError("Refusing to print a related pull request result that may contain credentials.")
    return rendered
