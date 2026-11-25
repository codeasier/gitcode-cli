"""Bounded issue-view JSON enrichment. Do not substitute the detail's integer count."""

from __future__ import annotations

import re
from typing import Any

from .._redact import redact
from ..errors import APIError
from ..repo_read import bounded_json_response, validate_target
from .issue_status import MAX_DATA_PAGES, PAGE_SIZE, IssuePagination


def _id(value: Any) -> int:
    if type(value) is int and 0 < value < 10**20:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return int(value)
    raise APIError("Invalid issue or comment identity.")


def _canonical_owner(detail: dict, owner: str, repo: str, number: str) -> str:
    # Do not parse a returned URL as a request target. Match only known canonical
    # issue spellings; owner case is an ASCII alias, slug and issue number are not.
    url = detail.get("html_url")
    match = (
        re.fullmatch(
            rf"https://(?:gitcode|(?:api\.)?atomgit)\.com/([A-Za-z0-9_][A-Za-z0-9_.-]{{0,254}})"
            rf"/{re.escape(repo)}/issues/{re.escape(number)}",
            url,
        )
        if isinstance(url, str)
        else None
    )
    if not match or not owner.isascii() or match[1].lower() != owner.lower():
        raise APIError("GitCode did not confirm the requested issue URL.")
    _verify_repository(detail.get("repository"), owner, repo)
    return match[1]


def _verify_repository(repository: Any, owner: str, repo: str) -> None:
    if repository is None:
        return
    if not isinstance(repository, dict) or repository.get("path", repo) != repo:
        raise APIError("Conflicting repository path in issue details.")
    for key in ("path_with_namespace", "full_path", "full_name"):
        if key not in repository:
            continue
        name = repository[key]
        if not isinstance(name, str) or name.count("/") != 1 or not name.isprintable():
            raise APIError("Invalid repository identity in issue details.")
        parts = name.split("/")
        if key == "full_name":
            # This field can contain display names. When a component contains
            # an interior space, it is not an authoritative path.
            parts = [p.strip(" ") for p in parts]
            if all(parts) and any(" " in p for p in parts):
                continue
        if not parts[0].isascii() or parts[0].lower() != owner.lower() or parts[1] != repo:
            raise APIError("Conflicting repository identity in issue details.")
    _verify_namespace(repository.get("namespace"), owner)


def _verify_namespace(namespace: Any, owner: str) -> None:
    if namespace is not None:
        if not isinstance(namespace, dict):
            raise APIError("Invalid issue repository namespace.")
        for key in ("path", "full_path"):
            if key in namespace:
                value = namespace[key]
                if not isinstance(value, str) or not value.isascii() or value.lower() != owner.lower():
                    raise APIError("Conflicting issue repository namespace.")


def _without_credential(data: Any, token: str) -> None:
    # Check decoded text (including escaped characters), without changing user-authored content.
    if isinstance(data, str):
        if redact(data, token) != data:
            raise APIError("Refusing to print a response that may contain credentials.")
    elif isinstance(data, dict):
        for key, value in data.items():
            _without_credential(key, token)
            _without_credential(value, token)
    elif isinstance(data, list):
        for entry in data:
            _without_credential(entry, token)


def _project(raw: Any, issue_id: int, number: int) -> dict:
    target = raw.get("target") if isinstance(raw, dict) else None
    issue = target.get("issue") if isinstance(target, dict) else None
    if not isinstance(issue, dict) or _id(issue.get("id")) != issue_id:
        raise APIError("Cannot verify the parent of an issue comment.")
    # The published v5 schema and its example spell number as 'nubmer'.
    numbers = {_id(issue[key]) for key in ("number", "nubmer") if key in issue}
    if numbers != {number}:
        raise APIError("Comment target does not match the requested issue number.")
    cid = _id(raw.get("id"))
    if not isinstance(raw.get("body"), str):
        raise APIError("Invalid issue comment body.")
    # Preserve GitCode's native comment fields, already exposed by --comments --json.
    # Add only aliases supported by the actual GitCode response, not GitHub-only fields.
    result = {key: raw[key] for key in ("body", "user", "target", "created_at", "updated_at") if key in raw}
    result["id"] = cid
    user = raw.get("user")
    author = {"login": user["login"]} if isinstance(user, dict) and isinstance(user.get("login"), str) else None
    result["author"] = author
    for field, native in (("createdAt", "created_at"), ("updatedAt", "updated_at")):
        result[field] = raw[native] if isinstance(raw.get(native), str) else None
    return result


def view_with_comments(owner: str, repo: str, number: str, token: str) -> dict:
    validate_target(owner, repo, None)
    expected = _id(number)
    endpoint = f"/repos/{owner}/{repo}/issues/{number}"
    detail, _, _ = bounded_json_response("Issue comments", endpoint, {}, token, (endpoint,))
    if not isinstance(detail, dict) or _id(detail.get("number")) != expected:
        raise APIError("GitCode did not confirm the requested issue.")
    issue_id = _id(detail.get("id"))
    canonical_owner = _canonical_owner(detail, owner, repo, number)
    endpoint = f"/repos/{canonical_owner}/{repo}/issues/{number}/comments"
    result: list[dict] = []
    seen: set[int] = set()
    pagination = IssuePagination()
    for page in range(1, MAX_DATA_PAGES + 2):
        params = {"page": str(page), "per_page": str(PAGE_SIZE)}
        rows, headers, url = bounded_json_response(
            "Issue comments", endpoint, params, token, (endpoint, *params, *params.values())
        )
        try:
            pagination.validate(rows, headers, url)
        except APIError:
            raise APIError("Incomplete or contradictory issue comment pagination.") from None
        if not rows:
            result_detail = {**detail, "comments": result}
            try:
                _without_credential(result_detail, token)
            except RecursionError:
                raise APIError("Issue comment response exceeded the nesting limit.") from None
            return result_detail
        if page > MAX_DATA_PAGES:
            raise APIError("Issue comment page limit reached; no partial result was printed.")
        for raw in rows:
            comment = _project(raw, issue_id, expected)
            if comment["id"] in seen:
                raise APIError("Repeated issue comment identity.")
            seen.add(comment["id"])
            result.append(comment)
    raise AssertionError("Unreachable: final page must be an empty probe.")
