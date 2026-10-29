"""Pure JSON output projections; never infer persisted state from request options."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


def json_number(value: Any) -> int | None:
    if type(value) is int:
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _web_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname.lower() == "api.gitcode.com"
        or re.match(r"^/api/v\d+(?:/|$)", parsed.path, re.IGNORECASE)
    ):
        return None
    return value


def _actor(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    login = value.get("login") or value.get("username") or value.get("name")
    return {
        "id": value.get("id"),
        "is_bot": bool(value.get("is_bot", False)),
        "login": login,
        "name": value.get("name") or login,
    }


def project_issue(item: dict) -> dict:
    result = dict(item)
    result["number"] = json_number(item.get("number"))
    state = _text(item.get("state"))
    state = state.upper() if state else None
    result["state"] = "OPEN" if state == "OPENED" else state
    result["url"] = next(
        (url for key in ("html_url", "web_url", "url") if (url := _web_url(item.get(key))) is not None), None
    )
    result["author"] = _actor(item.get("author") or item.get("user") or item.get("creator"))
    if "body" not in item:
        result["body"] = item.get("description")
    for camel, snake in (("createdAt", "created_at"), ("updatedAt", "updated_at"), ("closedAt", "closed_at")):
        result[camel] = _text(item.get(camel)) or _text(item.get(snake))
    return result


def _ref_fields(item: dict, result: dict, side: str, raw_name: str) -> None:
    original = item.get(side)
    ref = original.get("ref") if isinstance(original, dict) else original
    name = _text(ref) or _text(item.get(f"{side}RefName")) or _text(item.get(raw_name))
    oid = original.get("sha") if isinstance(original, dict) else None
    result[f"{side}RefName"] = name
    result[f"{side}RefOid"] = _text(oid) or _text(item.get(f"{side}RefOid"))
    if isinstance(original, dict):
        result[side] = {**original, "ref": name}
    elif name is not None:
        result[side] = {"ref": name}
    else:
        result[side] = None


def project_pr(item: dict) -> dict:
    result = project_issue(item)
    result["mergedAt"] = _text(item.get("mergedAt")) or _text(item.get("merged_at"))
    assignees = item.get("assignees")
    result["assignees"] = [_actor(value) for value in assignees] if isinstance(assignees, list) else assignees
    _ref_fields(item, result, "head", "source_branch")
    _ref_fields(item, result, "base", "target_branch")
    draft = item.get("draft")
    if type(draft) is not bool:
        draft = item.get("work_in_progress")
        if type(draft) is int and draft in (0, 1):
            draft = bool(draft)
    result["draft"] = draft if type(draft) is bool else None
    return result


def _path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return None
    parts = value.split("/")
    if any(not part or part in {".", ".."} or any(char in part for char in "\\?#") for part in parts):
        return None
    return value


def repo_name_with_owner(item: dict) -> str | None:
    path_with_namespace = _path(item.get("path_with_namespace"))
    if path_with_namespace and "/" in path_with_namespace:
        return path_with_namespace
    repo_path = _path(item.get("path"))
    namespace = item.get("namespace")
    owner = item.get("owner")
    owner_path = None
    if isinstance(namespace, dict):
        owner_path = _path(namespace.get("full_path")) or _path(namespace.get("path"))
    if owner_path is None and isinstance(owner, dict):
        owner_path = _path(owner.get("login")) or _path(owner.get("path"))
    if owner_path and repo_path and "/" not in repo_path:
        return f"{owner_path}/{repo_path}"
    full_name = _path(item.get("full_name"))
    return full_name if full_name and "/" in full_name else None
