"""Complete bounded collection for consumers that must not mistake partial data for empty."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ..errors import APIError


def collect_pages(client: GitCodeClient, path: str) -> list[Any]:
    items: list[Any] = []
    previous: list[Any] | None = None
    seen_ids: set[str] = set()
    for page in range(1, 101):
        result = client.get(path, params={"page": page, "per_page": 100})
        if not isinstance(result, list):
            raise APIError("Unexpected list response while collecting pages")
        if result and result == previous:
            raise APIError("Repeated pagination response")
        for item in result:
            if not isinstance(item, dict) or item.get("id") is None:
                raise APIError("Missing resource identity in pagination response")
            identity = str(item["id"])
            if identity in seen_ids:
                raise APIError("Duplicate resource identity across pagination response")
            seen_ids.add(identity)
        items.extend(result)
        if len(result) < 100:
            return items
        previous = result
    raise APIError("Pagination limit exceeded; collection is incomplete")
