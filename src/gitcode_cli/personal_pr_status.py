"""Read open PRs from the provider-defined authored queue. This is not gh pr status."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from ._redact import redact, redacted_transport
from .client import BASE_URL
from .errors import APIError, NetworkError
from .repo import validate_gitcode_repo
from .rest_api import open_client
from .services.issue_status import _Pagination
from .transport import ResponseTooLargeError, read_response_bytes

AUTHORED_SCOPE = "created_by_me"
PAGE_SIZE = 100
MAX_DATA_PAGES = 10
MAX_BYTES = 16 * 1024 * 1024  # combined response budget, not per page
MAX_REPO_BYTES = 1024 * 1024


@dataclass(frozen=True)
class PersonalPR:
    repository: str
    number: int
    title: str


@dataclass(frozen=True)
class _RepoIdentity:
    path: str
    id: int


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError
    return data


def _read_json(response: httpx.Response, remaining: int, source: str) -> tuple[Any, int]:
    if response.status_code != 200:
        raise APIError(f"GitCode {source} returned HTTP {response.status_code}.", response.status_code)
    if response.headers.get("content-encoding", "identity").lower() != "identity" or remaining <= 0:
        raise APIError(f"Cannot verify {source} within the response byte limit.")
    try:
        raw = read_response_bytes(response, max_response_bytes=remaining)
        return json.loads(raw, object_pairs_hook=_unique), len(raw)
    except ResponseTooLargeError:
        raise APIError(f"{source.capitalize()} exceeded the response byte limit.") from None
    except (ValueError, RecursionError):
        raise APIError(f"Invalid JSON in {source}.") from None


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _repo_path(path: object, token: str) -> str:
    if not isinstance(path, str) or path.count("/") != 1 or not path.isprintable() or "%" in path or token in path:
        raise APIError("Cannot verify a literal GitCode repository path for personal PR status.")
    owner, name = path.split("/")
    validate_gitcode_repo(None, owner, name)
    return path


def _case_variant(left: str, right: str) -> bool:
    # This only constrains the spelling returned by the provider, never decides
    # repository identity. Do not treat Unicode look-alikes as case aliases.
    return left == right or (left.isascii() and right.isascii() and left.lower() == right.lower())


def _check_repo_fields(repo: dict, path: str, alternate_names: tuple[str, ...]) -> None:
    name = path.split("/")[1]
    if repo.get("path", name) != name or any(repo.get(field, path) != path for field in alternate_names):
        raise APIError("Conflicting repository paths in personal PR status.")


def _repo_url(target: str, token: str) -> str:
    path = _repo_path(target, token)
    encoded = "/".join(quote(segment, safe="") for segment in path.split("/"))
    if token in encoded:
        raise APIError("Cannot send a GitCode token in the repository path.")
    return BASE_URL + "repos/" + encoded


def _resolve_target(
    client: httpx.Client, token: str, target: str, url: str, headers: dict[str, str], remaining: int
) -> tuple[_RepoIdentity, int]:
    client.cookies.clear()
    with client.stream("GET", url, headers=headers) as response:
        repo, used = _read_json(response, min(remaining, MAX_REPO_BYTES), "personal PR repository lookup")
    if not isinstance(repo, dict) or not _positive_int(repo.get("id")):
        raise APIError("Cannot verify a repository ID for personal PR status.")
    path = _repo_path(repo.get("full_name"), token)
    if not _case_variant(target, path):
        raise APIError("GitCode did not confirm the requested repository spelling.")
    # Repository detail's path is a single repo slug, not a full path.
    _check_repo_fields(repo, path, ("full_path", "path_with_namespace"))
    if "namespace" in repo:
        namespace = repo["namespace"]
        if not isinstance(namespace, dict) or namespace.get("path") != path.split("/")[0]:
            raise APIError("Conflicting repository namespace in personal PR status.")

    return _RepoIdentity(path, repo["id"]), used


def _base_identity(row: dict, token: str) -> tuple[str, int | None]:
    base = row.get("base")
    repo = base.get("repo") if isinstance(base, dict) else None
    if not isinstance(repo, dict):
        raise APIError("Cannot verify the base repository of a personal PR.")
    path = _repo_path(repo.get("full_path"), token)
    _check_repo_fields(repo, path, ("full_name", "path_with_namespace"))
    if (
        ("project_id" in row and not _positive_int(row["project_id"]))
        or ("id" in repo and not _positive_int(repo["id"]))
        or ("project_id" in row and "id" in repo and row["project_id"] != repo["id"])
    ):
        raise APIError("Conflicting or invalid base repository ID in personal PR status.")
    return path, repo.get("id")


def _row(item: object, token: str) -> tuple[PersonalPR, int | None]:
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
    path, repo_id = _base_identity(item, token)
    return PersonalPR(path, number, safe_title), repo_id


def _matches_target(
    target: _RepoIdentity, path: str, repo_id: int | None, ids: dict[str, int], paths: dict[int, str]
) -> bool:
    # A row can be excluded only if neither part of its identity points to
    # the target, and successive rows must not contradict earlier identities.
    if repo_id is None or ids.setdefault(path, repo_id) != repo_id or paths.setdefault(repo_id, path) != path:
        raise APIError("Missing or conflicting repository identity in personal PR status.")
    path_matches = path == target.path
    id_matches = repo_id == target.id
    if path_matches != id_matches or (not path_matches and _case_variant(path, target.path)):
        raise APIError("GitCode returned an ambiguous base repository for personal PR status.")
    return path_matches and id_matches


def personal_status(token: str, scope: str, target: str | None) -> tuple[str | None, list[PersonalPR]]:
    if not token or not token.isascii() or not token.isprintable() or any(c.isspace() for c in token):
        raise APIError("A valid GitCode token is required for personal PR status. Run 'gc auth login'.")
    if scope != AUTHORED_SCOPE:
        raise APIError("Invalid personal PR scope.")
    url = _repo_url(target, token) if target is not None else None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Accept-Encoding": "identity"}
    rows: list[PersonalPR] = []
    seen: set[tuple[str, int]] = set()
    pagination = _Pagination(page_size=PAGE_SIZE, source="personal PR status")
    remaining = MAX_BYTES
    identity = None
    ids: dict[str, int] = {}
    paths: dict[int, str] = {}
    try:
        with open_client() as client, redacted_transport(token):
            if target is not None and url is not None:
                identity, used = _resolve_target(client, token, target, url, headers, remaining)
                remaining -= used
            # Require an empty terminal page even when the server returned a short page.
            for page in range(1, MAX_DATA_PAGES + 2):
                params = {"scope": scope, "state": "open", "page": str(page), "per_page": str(PAGE_SIZE)}
                client.cookies.clear()
                with client.stream("GET", BASE_URL + "user/pulls", params=params, headers=headers) as response:
                    items, used = _read_json(response, remaining, "personal PR status")
                    pagination.validate(items, response.headers, response.url)
                remaining -= used
                if not items:
                    return identity.path if identity is not None else None, rows
                if page > MAX_DATA_PAGES:
                    break
                for item in items:
                    row, repo_id = _row(item, token)
                    key = (row.repository, row.number)
                    if key in seen:
                        raise APIError("Repeated personal PR identity; no partial result was returned.")
                    seen.add(key)
                    if identity is None or _matches_target(identity, row.repository, repo_id, ids, paths):
                        rows.append(row)
    except httpx.HTTPError:
        raise NetworkError("Could not read personal PR status; no partial result was returned.") from None
    raise APIError("Personal PR pagination limit reached; no partial result was returned.")
