from __future__ import annotations

import base64
import binascii
import re
from typing import Any
from urllib.parse import unquote

import click

from ..errors import APIError
from ..services import RepoService
from .base import AdapterActionResult

_README_BLOB_RE = re.compile(r"/blob/[^/]+/(?P<path>.+)$")


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


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if v is not None}


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
            match = _README_BLOB_RE.search(str(readme_url))
            if match:
                path = unquote(match.group("path"))
        try:
            data = self.service.contents(owner, repo, path)
        except APIError:
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
    ) -> list[dict[str, Any]]:
        has_filters = fork or source or bool(visibility) or bool(language)

        def matches(item: dict[str, Any]) -> bool:
            return (
                _matches_forkness(item, fork=fork, source=source)
                and _matches_visibility(item, visibility)
                and _matches_language(item, language)
            )

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
        item = self.service.fork(owner, repo, org=org)
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

    def sync_repo(self, owner: str, repo: str) -> AdapterActionResult:
        item = self.service.sync(owner, repo)
        return AdapterActionResult(item=item, message="synced")
