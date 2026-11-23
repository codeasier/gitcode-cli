"""Read a single provider-defined personal PR scope. This is not gh pr status."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from ._redact import redact, redacted_transport
from .client import BASE_URL
from .errors import APIError, NetworkError
from .repo import validate_gitcode_repo
from .rest_api import open_client
from .transport import ResponseTooLargeError, read_response_bytes

SCOPES = ("created_by_me", "assigned_to_me", "need_my_approve", "need_my_review")
PAGE_SIZE = 100
MAX_DATA_PAGES = 10
MAX_BYTES = 16 * 1024 * 1024  # combined response budget, not per page


@dataclass(frozen=True)
class PersonalPR:
    repository: str
    number: int
    title: str


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError
    return data


def _page(response: httpx.Response, remaining: int) -> tuple[list, int]:
    if response.status_code != 200:
        raise APIError(f"GitCode personal PR status returned HTTP {response.status_code}.", response.status_code)
    if response.headers.get("content-encoding", "identity").lower() != "identity" or remaining <= 0:
        raise APIError("Cannot verify personal PR status within the response byte limit.")
    try:
        raw = read_response_bytes(response, max_response_bytes=remaining)
        items = json.loads(raw, object_pairs_hook=_unique)
    except ResponseTooLargeError:
        raise APIError("Personal PR status exceeded the response byte limit.") from None
    except (ValueError, RecursionError):
        raise APIError("Invalid JSON in personal PR status.") from None
    if not isinstance(items, list) or len(items) > PAGE_SIZE:
        raise APIError("Invalid personal PR status page.")
    if not items and (response.headers.get("x-next-page") or "next" in response.links):
        raise APIError("Empty personal PR status page advertised a continuation.")
    return items, len(raw)


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _base_identity(row: dict, token: str) -> str:
    base = row.get("base")
    repo = base.get("repo") if isinstance(base, dict) else None
    path = repo.get("full_path") if isinstance(repo, dict) else None
    if (
        not isinstance(repo, dict)
        or not isinstance(path, str)
        or path.count("/") != 1
        or not path.isprintable()
        or "%" in path
        or any(repo.get(key, path) != path for key in ("full_name", "path_with_namespace"))
        or ("project_id" in row and not _positive_int(row["project_id"]))
        or ("id" in repo and not _positive_int(repo["id"]))
        or ("project_id" in row and "id" in repo and row["project_id"] != repo["id"])
        or token in path
    ):
        raise APIError("Cannot verify the base repository of a personal PR.")
    owner, name = path.split("/")
    if repo.get("path", name) != name:
        raise APIError("Conflicting base repository paths in personal PR status.")
    validate_gitcode_repo(None, owner, name)
    return path


def _row(item: object, token: str) -> PersonalPR:
    if not isinstance(item, dict) or item.get("state") != "open":
        raise APIError("Cannot verify an open PR in the personal status response.")
    number, title = item.get("number"), item.get("title")
    if (
        type(number) is not int
        or number < 1
        or ("iid" in item and (not _positive_int(item["iid"]) or item["iid"] != number))
    ):
        raise APIError("Cannot verify a personal PR number.")
    if not isinstance(title, str) or not title.strip():
        raise APIError("Missing personal PR title.")
    # No bodies, actors, raw URLs or control characters in terminal output.
    safe_title = "".join(c if c.isprintable() else ascii(c)[1:-1] for c in redact(title, token))
    return PersonalPR(_base_identity(item, token), number, safe_title)


def personal_status(token: str, scope: str, target: str | None) -> list[PersonalPR]:
    if not token or not token.isascii() or not token.isprintable() or any(c.isspace() for c in token):
        raise APIError("A valid GitCode token is required for personal PR status. Run 'gc auth login'.")
    if scope not in SCOPES:
        raise APIError("Invalid personal PR scope.")
    if target is not None and (not target.isprintable() or "%" in target or token in target):
        raise APIError("Expected a literal GitCode repository for personal PR status.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Accept-Encoding": "identity"}
    rows: list[PersonalPR] = []
    seen: set[tuple[str, int]] = set()
    remaining = MAX_BYTES
    try:
        with open_client() as client, redacted_transport(token):
            # Require an empty terminal page even when the server returned a short page.
            for page in range(1, MAX_DATA_PAGES + 2):
                params = {"scope": scope, "state": "open", "page": str(page), "per_page": str(PAGE_SIZE)}
                client.cookies.clear()
                with client.stream("GET", BASE_URL + "user/pulls", params=params, headers=headers) as response:
                    items, used = _page(response, remaining)
                remaining -= used
                if not items:
                    return rows
                if page > MAX_DATA_PAGES:
                    break
                for item in items:
                    row = _row(item, token)
                    key = (row.repository, row.number)
                    if key in seen:
                        raise APIError("Repeated personal PR identity; no partial result was returned.")
                    seen.add(key)
                    if target is None or target == row.repository:
                        rows.append(row)
    except httpx.HTTPError:
        raise NetworkError("Could not read personal PR status; no partial result was returned.") from None
    raise APIError("Personal PR pagination limit reached; no partial result was returned.")
