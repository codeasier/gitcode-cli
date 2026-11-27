"""Observe bounded native label pages; return the existing exact-total local slice."""

from __future__ import annotations

import re
from typing import Any

import httpx

from .api import API_BASE_URL, GitCodeAPI, GitCodeError

PAGE_SIZE = 100
MAX_DATA_PAGES = 10
_NOTE = (
    "A bounded scan of native label pages was verified through an empty page. "
    "Each call scans the current catalog; pages are not a stable snapshot."
)
_LINK = re.compile(
    r'\s*<([^<>\s]+)>\s*;\s*rel\s*=\s*(?:"(next|prev|first|last)"|(next|prev|first|last))\s*'
)


def _invalid() -> GitCodeError:
    return GitCodeError(
        "invalid_response", "Could not verify the complete repository label catalog."
    )


def _size(value: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", value):
        raise _invalid()
    return int(value)


def _links(headers: httpx.Headers, path: str) -> dict[str, int]:
    # Accept only evidence for this exact numbered request series. Do not follow URLs.
    absolute = API_BASE_URL + path.lstrip("/")
    allowed = {"", absolute, httpx.URL(absolute).path}
    result: dict[str, int] = {}
    for field in headers.get_list("link"):
        for part in field.split(","):
            match = _LINK.fullmatch(part)
            if match is None:
                raise _invalid()
            target, _, query = match[1].partition("?")
            relation = match[2] or match[3]
            if target not in allowed or relation in result:
                raise _invalid()
            params = sorted(query.split("&"))
            if (
                len(params) != 2
                or not params[0].startswith("page=")
                or params[1] != f"per_page={PAGE_SIZE}"
            ):
                raise _invalid()
            value = _size(params[0][5:])
            if value == 0:
                raise _invalid()
            result[relation] = value
    return result


def _consistent(previous: int | None, claim: str | None, bound: int) -> int | None:
    if claim is None:
        return previous
    value = _size(claim)
    if value > bound or (previous is not None and previous != value):
        raise _invalid()
    return value


def label_page(api: GitCodeAPI, path: str, *, page: int, per_page: int) -> dict[str, Any]:
    if api.token and api.token in path:
        raise GitCodeError("invalid_arguments", "Label target must not contain credentials.")
    ids: set[int] = set()
    names: set[str] = set()
    data = []
    start = (page - 1) * per_page
    repository_id = total = last = None
    expect_more = ended = False
    used_bytes = 0
    for number in range(1, MAX_DATA_PAGES + 2):
        rows, h, size = api.request(
            "GET",
            path,
            params={"page": number, "per_page": PAGE_SIZE},
            _page_budget=api.max_response_bytes - used_bytes,
        )
        used_bytes += size
        if (
            not isinstance(rows, list)
            or len(rows) > PAGE_SIZE
            or "content-range" in h
            or h.get("x-page", str(number)) != str(number)
            or h.get("x-per-page", str(PAGE_SIZE)) != str(PAGE_SIZE)
            or any(
                h.get(k, "false").strip().lower() not in {"false", "0"}
                for k in ("x-truncated", "x-incomplete-results")
            )
        ):
            raise _invalid()
        links = _links(h, path)
        total = _consistent(total, h.get("x-total"), MAX_DATA_PAGES * PAGE_SIZE)
        last = _consistent(last, h.get("x-total-pages"), MAX_DATA_PAGES)
        if "last" in links:
            last = _consistent(last, str(links["last"]), MAX_DATA_PAGES)
        advertised = h.get("x-next-page")
        if (
            advertised not in (None, "", str(number + 1))
            or ("next" in links and (links["next"] != number + 1 or advertised == ""))
            or links.get("first", 1) != 1
            or ("prev" in links and (number == 1 or links["prev"] != number - 1))
            or ("x-prev-page" in h and h["x-prev-page"] != ("" if number == 1 else str(number - 1)))
        ):
            raise _invalid()
        has_next = bool(advertised) or "next" in links
        if not rows:
            if (
                expect_more
                or has_next
                or (total is not None and total != len(ids))
                or (last is not None and last != number - 1 and not (number == 1 == last))
            ):
                raise _invalid()
            return {
                "data": data,
                "page": page,
                "per_page": per_page,
                "next_page": page + 1 if start + per_page < len(ids) else None,
                "pagination_mode": "client",
                "total_items": len(ids),
                "pagination_note": _NOTE,
            }
        if ended or number > MAX_DATA_PAGES or (last is not None and number > last):
            raise _invalid()
        for row in rows:
            if not isinstance(row, dict):
                raise _invalid()
            key, name = row.get("id"), row.get("name")
            if (
                type(key) is not int
                or key <= 0
                or key in ids
                or not isinstance(name, str)
                or not name.strip()
                or not name.isprintable()
                or name in names
            ):
                raise _invalid()
            if "repository_id" in row:
                current = row["repository_id"]
                if type(current) is not int or current <= 0 or repository_id not in (None, current):
                    raise _invalid()
                repository_id = current
            if start <= len(ids) < start + per_page:
                data.append(row)
            ids.add(key)
            names.add(name)
        ended = advertised == "" or total == len(ids) or last == number
        if (total is not None and len(ids) > total) or (ended and has_next):
            raise _invalid()
        expect_more = has_next
    raise _invalid()
