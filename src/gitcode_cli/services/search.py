"""GitCode v5 keyword search. All three documented endpoints return arrays, not envelopes."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ..errors import APIError

# The page ceilings are endpoint-specific; keep per_page fixed across pages
# so a non-multiple --limit does not change the offset of the last request.
PAGE_SIZES = {"repositories": 20, "issues": 50, "users": 50}
MAX_PAGES = 100


class SearchService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def search(self, resource: str, keyword: str, limit: int, **filters: Any) -> list[dict]:
        if resource not in PAGE_SIZES:
            raise ValueError("Unknown GitCode search resource")
        if not keyword.strip() or not 1 <= limit <= PAGE_SIZES[resource] * MAX_PAGES:
            raise ValueError("Search keyword or result limit is out of range")
        params = {k: v for k, v in filters.items() if v is not None}
        per_page = min(limit, PAGE_SIZES[resource])
        rows: list[dict] = []
        seen: set[str] = set()
        for page in range(1, (limit + per_page - 1) // per_page + 1):
            data = self.client.get(
                f"/search/{resource}", params={**params, "q": keyword, "page": page, "per_page": per_page}
            )
            if not isinstance(data, list) or len(data) > per_page:
                raise APIError("Unexpected GitCode search response; expected a page of results.")
            for item in data:
                if not isinstance(item, dict) or type(item.get("id")) not in (int, str) or not str(item["id"]):
                    raise APIError("Missing identity in GitCode search result.")
                identity = str(item["id"])
                if identity in seen:
                    raise APIError("GitCode returned overlapping search pages; repeat the search.")
                seen.add(identity)
                rows.append(item)
            if len(data) < per_page:
                break
        return rows[:limit]


# Use the documented default pp as a conservative page size, not an alleged
# AtomGit maximum. The page ceiling for this endpoint is imposed locally.
PULL_PAGE_SIZE = 10
MAX_PULL_RESULTS = PULL_PAGE_SIZE * MAX_PAGES


def _pull_page(body: Any, page: int, per_page: int) -> tuple[list[Any], int]:
    if not isinstance(body, dict):
        raise APIError("Expected a GitCode pull request search page.")
    response_page, size, total, pages = (body.get(key) for key in ("page_num", "page_size", "total", "page_count"))
    if (
        type(response_page) is not int
        or response_page != page
        or type(size) is not int
        or size != per_page
        or type(total) is not int
        or total < 0
        or type(pages) is not int
        or pages != (total + per_page - 1) // per_page
    ):
        raise APIError("Invalid GitCode pull request search pagination metadata.")
    content = body.get("content")
    expected = min(per_page, max(0, total - per_page * (page - 1)))
    if not isinstance(content, list) or len(content) != expected:
        raise APIError("Incomplete or malformed GitCode pull request search page.")
    return content, pages


def _pull_identity(item: Any) -> tuple[str, str | int]:
    if isinstance(item, dict):
        identity = item.get("id")
        if isinstance(identity, str) and identity:
            return ("", identity)
        # The typed search contract allows id to be null.
        repo = item.get("path_with_namespace")
        number = item.get("iid")
        if isinstance(repo, str) and repo and type(number) is int and number > 0:
            return (repo, number)
    raise APIError("Missing identity in GitCode pull request search result.")


def search_pulls(
    client: GitCodeClient,
    keyword: str,
    limit: int,
    *,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict]:
    """Call the typed search API, never falling back to a scan or another host."""
    if not keyword.strip() or not 1 <= limit <= MAX_PULL_RESULTS:
        raise ValueError("Search keyword or result limit is out of range")
    per_page = min(limit, PULL_PAGE_SIZE)
    params: dict[str, Any] = {"type": "pullrequest", "q": keyword, "pp": per_page}
    params.update({key: value for key, value in (("s", sort), ("o", order)) if value is not None})
    rows: list[dict] = []
    seen: set[tuple[str, str | int]] = set()
    for page in range(1, (limit + per_page - 1) // per_page + 1):
        content, pages = _pull_page(client.get("/search", params={**params, "p": page}), page, per_page)
        for item in content:
            identity = _pull_identity(item)
            if identity in seen:
                raise APIError("GitCode returned overlapping pull request search pages; repeat the search.")
            seen.add(identity)
            rows.append(item)
        if page >= pages:
            break
    return rows[:limit]
