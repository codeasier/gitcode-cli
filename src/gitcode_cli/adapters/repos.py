from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable, Iterator
from functools import partial
from typing import Any
from urllib.parse import unquote, urlsplit

import click

from ..config import valid_login
from ..errors import APIError
from ..json_projection import json_number, repo_is_archived
from ..repo import is_single_ref, validate_gitcode_repo
from ..services import RepoService
from .base import AdapterActionResult

_README_BLOB_RE = re.compile(r"/blob/[^/]+/(?P<path>.+)$")
_ARCHIVE_PAGE_SIZE = 100
_ARCHIVE_MAX_PAGES = 100


def _as_list(items: Any) -> list[Any]:
    return items if isinstance(items, list) else []


def _repo_visibility(item: dict[str, Any]) -> str:
    if item.get("private"):
        return "private"
    if item.get("internal"):
        return "internal"
    return "public"


def _matches_visibility(item: dict[str, Any], visibility: str | None) -> bool:
    if not visibility:
        return True
    return _repo_visibility(item) == visibility.lower()


def _matches_language(item: dict[str, Any], language: str | None) -> bool:
    if not language:
        return True
    return str(item.get("language") or "").lower() == language.lower()


def _matches_forkness(item: dict[str, Any], *, fork: bool, source: bool) -> bool:
    is_fork = bool(item.get("fork"))
    if fork and not is_fork:
        return False
    return not (source and is_fork)


def _flag(value: Any) -> bool | None:
    return bool(value) if type(value) in (int, bool) and value in (0, 1) else None


def _visibility_matches_evidence(item: dict, wanted: str) -> bool | None:
    flags = {k: _flag(item.get(k)) for k in ("public", "private", "internal")}
    if any(item.get(k) is not None and flags[k] is None for k in flags):
        return None
    possible = {k for k, v in flags.items() if v is not False}
    explicit = {k for k, v in flags.items() if v is True}
    if len(explicit) > 1 or not possible:
        return None
    if explicit:
        return wanted in explicit
    if wanted not in possible:
        return False
    return True if len(possible) == 1 else None


def _matches_archive_filters(
    item: dict, archived: bool, *, fork: bool, source: bool, visibility: str | None, language: str | None
) -> bool:
    state = repo_is_archived(item, from_list=True)
    checks: list[bool | None] = [state is archived if state is not None else None]
    if fork or source:
        flag = _flag(item.get("fork"))
        checks.append(flag is fork if flag is not None else None)
    if visibility:
        checks.append(_visibility_matches_evidence(item, visibility))
    if language:
        value = item.get("language")
        checks.append(value.lower() == language.lower() if isinstance(value, str) else None)
    if False in checks:
        return False
    if state is None:
        raise click.ClickException(
            "Cannot filter repositories with unknown or conflicting archive state. "
            "Run without the archive filter and inspect --json nameWithOwner,isArchived."
        )
    if None in checks:
        raise click.ClickException("Cannot verify the combined repository filters from GitCode list data.")
    return True


def _archive_rows(fetch: Callable[..., Any]) -> Iterator[dict]:
    seen: set[int] = set()
    for page in range(1, _ARCHIVE_MAX_PAGES + 1):
        rows = fetch(page=page, per_page=_ARCHIVE_PAGE_SIZE)
        if not isinstance(rows, list) or len(rows) > _ARCHIVE_PAGE_SIZE:
            raise APIError("Invalid GitCode repository list response.")
        # Validate identities across the entire fetched page before letting a
        # consumer reach its match limit, including the unused tail of the page.
        for row in rows:
            if not isinstance(row, dict):
                raise APIError("Invalid GitCode repository list response.")
            identity = json_number(row.get("id"))
            if identity is None or identity in seen:
                raise APIError("Missing, invalid or repeated identity in GitCode repository list response.")
            seen.add(identity)
        yield from rows
        if len(rows) < _ARCHIVE_PAGE_SIZE:
            return
    raise APIError("Repository list page safety limit reached; result would be incomplete.")


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if v is not None}


def _confirmed_fork_full_name(item: Any, organization: str, repo: str) -> str:
    """Use the same confirmed canonical destination for success and optional clone."""
    namespaces: list[str] = []
    name = repo
    malformed_name = False
    if isinstance(item, dict):
        namespace = item.get("namespace")
        if isinstance(namespace, dict):
            path = namespace.get("full_path") or namespace.get("path")
            if isinstance(path, str) and path:
                namespaces.append(path)
        full_name = item.get("full_name")
        if full_name is not None:
            if isinstance(full_name, str) and "/" in full_name:
                path, name = full_name.rsplit("/", 1)
                namespaces.append(path)
            else:
                malformed_name = True
        elif item.get("path") is not None:
            name = item["path"]
    if (
        malformed_name
        or not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or any(char.isspace() or ord(char) < 32 or char in "/\\?#" for char in name)
        or not namespaces
        or any(path != organization for path in namespaces)
    ):
        raise click.ClickException(
            "Fork destination did not confirm the requested organization. "
            "The request may have created a fork; verify your GitCode repositories before retrying. "
            "No clone was attempted."
        )
    return f"{organization}/{name}"


class RepoAdapter:
    def __init__(self, service: RepoService):
        self.service = service

    # --- read ---

    def view(self, owner: str, repo: str) -> dict[str, Any] | None:
        return self.service.get(owner, repo)

    def get_readme(self, owner: str, repo: str, item: dict[str, Any] | None = None) -> str | None:
        """Best-effort README fetch; returns None when it cannot be resolved."""
        path = "README.md"
        readme_url = item.get("readme_url") if isinstance(item, dict) else None
        if readme_url:
            try:
                readme_path = urlsplit(str(readme_url)).path
            except ValueError:
                return None
            match = _README_BLOB_RE.search(readme_path)
            if match:
                # URL decoding belongs here; FileService owns API path encoding.
                path = unquote(match.group("path"))
        try:
            data = self.service.contents(owner, repo, path)
        except (APIError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        content = data.get("content")
        if not isinstance(content, str) or not content:
            return None
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace").strip() or None
        except (binascii.Error, ValueError):
            return None

    def list_repos(
        self,
        owner: str | None,
        *,
        limit: int | None,
        fork: bool,
        source: bool,
        visibility: str | None,
        language: str | None,
        archived: bool | None = None,
    ) -> list[dict[str, Any]]:
        has_filters = fork or source or bool(visibility) or bool(language)

        def matches(item: dict[str, Any]) -> bool:
            return (
                _matches_forkness(item, fork=fork, source=source)
                and _matches_visibility(item, visibility)
                and _matches_language(item, language)
            )

        if archived is not None:
            if owner is not None and not valid_login(owner):
                raise click.UsageError("Archive filters require a literal GitCode username or organization path.")
            # Filter before truncating. An unknown row that could affect the result is
            # an error, not a match or a non-match. Stop filtering at the limit.
            found: list[dict[str, Any]] = []
            for item in _archive_rows(self._archive_fetcher(owner)):
                if _matches_archive_filters(
                    item, archived, fork=fork, source=source, visibility=visibility, language=language
                ):
                    found.append(item)
                    if len(found) == limit:
                        break
            return found

        per_page = 100 if limit is None else min(limit, 100)
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            page_items = _as_list(self._list_page(owner, page=page, per_page=per_page))
            if not page_items:
                break
            items.extend(item for item in page_items if not has_filters or matches(item))
            if len(page_items) < per_page:
                break
            if limit is not None and len(items) >= limit:
                break
            page += 1
        if limit is not None:
            return items[:limit]
        return items

    def _list_page(self, owner: str | None, **params: Any) -> Any | None:
        if owner is None:
            return self.service.list_own(**params)
        try:
            return self.service.list_user(owner, **params)
        except APIError as exc:
            if exc.status_code != 404:
                raise
            return self.service.list_org(owner, **params)

    def _archive_fetcher(self, owner: str | None) -> Callable[..., Any]:
        if owner is None:
            return self.service.list_own
        fetch = partial(self.service.list_user, owner)

        def fixed_scope(*, page: int, per_page: int) -> Any:
            nonlocal fetch
            try:
                return fetch(page=page, per_page=per_page)
            except APIError as exc:
                if page != 1 or exc.status_code != 404:
                    raise
                fetch = partial(self.service.list_org, owner)
                return fetch(page=page, per_page=per_page)

        return fixed_scope

    # --- write ---

    def create_repo(
        self,
        name: str,
        owner: str | None = None,
        *,
        description: str | None = None,
        private: bool | None = None,
        auto_init: bool = False,
        homepage: str | None = None,
        has_issues: bool | None = None,
        has_wiki: bool | None = None,
        gitignore_template: str | None = None,
        license_template: str | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        if private is not None:
            payload["private"] = private
        if auto_init:
            payload["auto_init"] = True
        if homepage is not None:
            payload["homepage"] = homepage
        if has_issues is not None:
            payload["has_issues"] = has_issues
        if has_wiki is not None:
            payload["has_wiki"] = has_wiki
        if gitignore_template is not None:
            payload["gitignore_template"] = gitignore_template
        if license_template is not None:
            payload["license_template"] = license_template
        if owner:
            return self.service.create_org(owner, **payload)
        return self.service.create_personal(**payload)

    def fork_repo(self, owner: str, repo: str, *, org: str | None = None) -> AdapterActionResult:
        organization = org.strip() if org is not None else None
        if organization == "":
            raise click.UsageError("--org must specify a nonempty organization path")
        item = self.service.fork(owner, repo, organization=organization)
        if organization is not None:
            full_name = _confirmed_fork_full_name(item, organization, repo)
            assert isinstance(item, dict)
            item = {**item, "full_name": full_name}
        return AdapterActionResult(item=item, message="forked")

    def edit_repo(
        self,
        owner: str,
        repo: str,
        *,
        description: str | None = None,
        homepage: str | None = None,
        default_branch: str | None = None,
        private: bool | None = None,
        has_issues: bool | None = None,
        has_wiki: bool | None = None,
    ) -> dict[str, Any] | None:
        payload = _drop_none(
            {
                "description": description,
                "homepage": homepage,
                "default_branch": default_branch,
                "private": private,
                "has_issues": has_issues,
                "has_wiki": has_wiki,
            }
        )
        if not payload:
            raise click.UsageError("must specify at least one field to edit")
        return self.service.update(owner, repo, **payload)

    def rename_repo(self, owner: str, repo: str, new_name: str) -> AdapterActionResult:
        item = self.service.update(owner, repo, name=new_name, path=new_name)
        return AdapterActionResult(item=item, message="renamed")

    def delete_repo(self, owner: str, repo: str) -> AdapterActionResult:
        self.service.delete(owner, repo)
        return AdapterActionResult(message="deleted")

    def sync_repo(self, owner: str, repo: str, *, branch: str | None = None) -> AdapterActionResult:
        current = self.service.get(owner, repo)
        fork = current.get("fork") if isinstance(current, dict) else None
        # Official schema uses integer flags, while its concrete example uses bool.
        # Do not coerce missing values, strings, floats or arbitrary integers.
        if type(fork) not in (bool, int) or fork not in (0, 1):
            raise click.ClickException(
                f"Cannot verify whether {owner}/{repo} is a fork; no synchronization request was sent."
            )
        if not fork:
            raise click.ClickException(f"Repository {owner}/{repo} is not a fork; no synchronization request was sent.")
        if branch is None:
            # gh defaults to the upstream's default, not the destination's. GitCode
            # interprets an omitted branch as *all* branches, never send that.
            parent = current.get("parent")
            nested = parent.get("full_name") if isinstance(parent, dict) else None
            flat = current.get("parentfull_name")
            name = nested or flat
            if not isinstance(name, str) or name.count("/") != 1 or (nested and flat and flat != nested):
                raise click.ClickException("Cannot verify the upstream repository; specify --branch. No sync was sent.")
            parent_owner, parent_repo = name.split("/")
            validate_gitcode_repo(None, parent_owner, parent_repo)
            upstream = self.service.get(parent_owner, parent_repo)
            branch = upstream.get("default_branch") if isinstance(upstream, dict) else None
        if not is_single_ref(branch):
            raise click.ClickException("Cannot verify a single branch to sync; specify --branch. No sync was sent.")
        item = self.service.sync(owner, repo, branch=branch)
        if not isinstance(item, dict) or item.get("repo_sync_result") is not True:
            raise click.ClickException("GitCode did not confirm synchronization. Check the fork before retrying.")
        return AdapterActionResult(item=item, message="synced")
