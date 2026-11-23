"""One page of organization Kanban summaries, not GitHub Projects."""

from __future__ import annotations

import re
from typing import Any

from ..errors import APIError
from ..rest_api import fetch

FIELDS = ("id", "iid", "name", "status", "visibility")
MAX_PAGE = 10000
MAX_PER_PAGE = 100


def _valid_text(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _project(body: Any, per_page: int, *, public_only: bool) -> list[dict[str, Any]]:
    if not isinstance(body, dict) or any(
        type(body.get(k)) is not int or body[k] < 0 for k in ("all_count", "open_count", "close_count")
    ):
        raise APIError("Malformed organization dashboard page.")
    content = body.get("content")
    if not isinstance(content, list) or len(content) > per_page:
        raise APIError("Malformed or oversized organization dashboard page.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in content:
        if not isinstance(item, dict) or not all(_valid_text(item.get(k)) for k in ("id", "name")):
            raise APIError("Malformed dashboard identity or name.")
        if item["id"] in seen or any(type(item.get(k)) is not int for k in ("iid", "status", "visibility")):
            raise APIError("Repeated dashboard or malformed numeric fields.")
        if item["status"] not in (0, 1) or item["visibility"] not in (1, 2):
            raise APIError("Unknown dashboard status or visibility.")
        if public_only and item["visibility"] != 1:
            raise APIError("Anonymous dashboard response contained a nonpublic board; no results returned.")
        seen.add(item["id"])
        result.append({k: item[k] for k in FIELDS})
    return result


def dashboard_page(org: str, page: int, per_page: int, *, token: str) -> list[dict[str, Any]]:
    # A single decoded path component only. Do not accept URL or repository selectors.
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,254}", org):
        raise APIError("Use a single organization slug for --org, not a URL, repository or nested path.")
    if (
        type(page) is not int
        or not 1 <= page <= MAX_PAGE
        or type(per_page) is not int
        or not 1 <= per_page <= MAX_PER_PAGE
    ):
        raise APIError("Dashboard pagination is out of range.")
    query = {"page": str(page), "per_page": str(per_page)}
    if not token:
        query["visibility"] = "1"
    (response,) = fetch(
        f"org/{org}/kanban/list",
        "v5",
        "GET",
        token,
        (),
        query,
        None,
        paginate=False,
        strict_json=True,
    )
    if response.status != 200:
        raise APIError(f"Unexpected dashboard HTTP status: {response.status}.", response.status)
    return _project(response.data, per_page, public_only=not token)
