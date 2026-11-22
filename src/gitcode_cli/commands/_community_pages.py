"""Validate numbered GitCode pages and stop fetching when a consumer has enough rows."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from ..errors import APIError

_MAX_PAGES = 100


def page_rows(fetch: Callable[..., Any], per_page: int, *, identity: str = "id") -> Iterator[dict]:
    seen: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        rows = fetch(page=page, per_page=per_page)
        if not isinstance(rows, list) or len(rows) > per_page:
            raise APIError("Invalid GitCode list response.")
        for row in rows:
            key = row.get(identity) if isinstance(row, dict) else None
            if type(key) not in (str, int) or not str(key).strip() or str(key) in seen:
                raise APIError("Missing or repeated identity in GitCode list response.")
            seen.add(str(key))
            yield row
        if len(rows) < per_page:
            return
    raise APIError("Page safety limit reached; result would be incomplete.")
