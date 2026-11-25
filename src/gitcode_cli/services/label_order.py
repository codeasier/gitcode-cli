"""Read and order an entire bounded label catalog; never sort an already limited prefix."""

from __future__ import annotations

import re

import httpx

from .._redact import redact
from ..errors import APIError
from ..repo_read import bounded_json_response, validate_target
from .issue_status import _continuation_links, _linked_page

PAGE_SIZE = 100
MAX_DATA_PAGES = 10
_INCOMPLETE = "Cannot verify a complete repository label catalog; no sorted results returned."


def _total(headers: httpx.Headers, key: str, previous: int | None) -> int | None:
    if key not in headers:
        return previous
    raw = headers[key]
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", raw) or (previous is not None and int(raw) != previous):
        raise APIError(_INCOMPLETE)
    return int(raw)


def _link_pages(headers: httpx.Headers, url: httpx.URL) -> dict[str, int]:
    # Check the same numbered route and query that we would derive locally.
    # This is evidence only; never use a link as a request destination.
    try:
        return {
            relation: _linked_page(target, url)
            for relation, target in _continuation_links(headers).items()
            if relation in ("next", "last")
        }
    except APIError:
        raise APIError(_INCOMPLETE) from None


def _collect(rows: list, catalog: dict[int, dict], names: set[str], repo_id: int | None, token: str) -> int | None:
    for row in rows:
        if not isinstance(row, dict):
            raise APIError(_INCOMPLETE)
        identity, name, color = row.get("id"), row.get("name"), row.get("color")
        if (
            type(identity) is not int
            or identity <= 0
            or identity in catalog
            or not isinstance(name, str)
            or not name.strip()
            or not name.isprintable()
            or name in names
            or redact(name, token) != name
            or (
                color is not None
                and (
                    not isinstance(color, str)
                    or not re.fullmatch(r"#?(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", color)
                    or redact(color, token) != color
                )
            )
        ):
            raise APIError(_INCOMPLETE)
        if "repository_id" in row:
            current = row["repository_id"]
            if type(current) is not int or current <= 0 or (repo_id is not None and current != repo_id):
                raise APIError(_INCOMPLETE)
            repo_id = current
        catalog[identity] = {"id": identity, "name": name, "color": color}
        names.add(name)
    return repo_id


def name_ordered_labels(owner: str, repo: str, *, token: str, descending: bool, limit: int) -> list[dict]:
    validate_target(owner, repo, None)
    endpoint = f"/repos/{owner}/{repo}/labels"
    catalog: dict[int, dict] = {}
    names: set[str] = set()
    repo_id = total = pages = None
    expect_data = ended = False
    # Even a short page is not evidence of exhaustion. Probe the next numbered
    # page, never a provider-supplied URL. The probe after the bound must be empty.
    for number in range(1, MAX_DATA_PAGES + 2):
        query = {"page": str(number), "per_page": str(PAGE_SIZE)}
        rows, headers, url = bounded_json_response(
            "Repository labels", endpoint, query, token, (endpoint, *query, *query.values())
        )
        if (
            not isinstance(rows, list)
            or len(rows) > PAGE_SIZE
            or headers.get("x-page", str(number)) != str(number)
            or headers.get("x-per-page", str(PAGE_SIZE)) != str(PAGE_SIZE)
            or "content-range" in headers
            or any(
                headers.get(k, "false").strip().lower() not in ("false", "0")
                for k in ("x-truncated", "x-incomplete-results")
            )
        ):
            raise APIError(_INCOMPLETE)
        total = _total(headers, "x-total", total)
        pages = _total(headers, "x-total-pages", pages)
        next_page = headers.get("x-next-page")
        links = _link_pages(headers, url)
        last_page = links.get("last")
        if (
            next_page not in (None, "", str(number + 1))
            or ("next" in links and (links["next"] != number + 1 or next_page == ""))
            or (last_page is not None and pages not in (None, last_page))
        ):
            raise APIError(_INCOMPLETE)
        if last_page is not None:
            pages = last_page
        has_next = "next" in links or bool(next_page)
        if not rows:
            if expect_data or has_next or (total is not None and total != len(catalog)):
                raise APIError(_INCOMPLETE)
            # All preceding requests had rows, so this probe is exactly
            # one past the last data page (or an empty page-one catalog).
            if pages is not None and pages != number - 1 and not (number == 1 == pages):
                raise APIError(_INCOMPLETE)
            return sorted(catalog.values(), key=lambda r: r["name"], reverse=descending)[:limit]
        if ended or number > MAX_DATA_PAGES or (pages is not None and number > pages):
            raise APIError(_INCOMPLETE)
        repo_id = _collect(rows, catalog, names, repo_id, token)
        if total is not None and len(catalog) > total:
            raise APIError(_INCOMPLETE)
        ended = next_page == "" or pages == number or total == len(catalog)
        if ended and has_next:
            raise APIError(_INCOMPLETE)
        expect_data = has_next
    raise APIError(_INCOMPLETE)
