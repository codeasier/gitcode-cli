from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import click

from ..errors import APIError, GCError
from ..json_projection import json_number
from ..services import IssueService, PullRequestService, UserService
from ._current_user import resolve_me
from ._milestones import milestone_number, resolve_pr_milestone
from ._pr_labels import PRLabelPlan
from ._pr_people import PRPeoplePlan
from .base import AdapterActionResult
from .capabilities import capability_message, unsupported


def _normalize_multi_values(values: tuple[str, ...] | None) -> str | None:
    if not values:
        return None
    return ",".join(values)


def _normalize_limit(limit: int | None) -> tuple[int, int | None]:
    if limit is None:
        return 30, 30
    if limit < 0:
        return 100, None
    if limit == 0:
        return 0, 0
    return min(limit, 100), limit


def _comment_user_identity(user: Any) -> tuple[str | None, str | None]:
    error = capability_message("PR_COMMENT_OWNERSHIP_UNVERIFIABLE")
    if not isinstance(user, dict):
        raise click.ClickException(error)
    user_id = user.get("id")
    login = user.get("login")
    if user_id is not None and (
        isinstance(user_id, bool) or not isinstance(user_id, (str, int)) or not str(user_id).strip()
    ):
        raise click.ClickException(error)
    if login is not None and (not isinstance(login, str) or not login.strip()):
        raise click.ClickException(error)
    if user_id is None and login is None:
        raise click.ClickException(error)
    return str(user_id) if user_id is not None else None, login


def _comment_creation_key(comment: dict[str, Any]) -> tuple[datetime, int]:
    comment_id = comment.get("id")
    if (
        isinstance(comment_id, bool)
        or not isinstance(comment_id, (int, str))
        or not str(comment_id).isascii()
        or not str(comment_id).isdigit()
    ):
        raise click.ClickException("Unable to identify the last pull request comment.")
    if int(comment_id) <= 0:
        raise click.ClickException("Unable to identify the last pull request comment.")
    created_at = comment.get("created_at")
    try:
        if not isinstance(created_at, str):
            raise ValueError
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise click.ClickException("Unable to determine the last pull request comment's creation time.") from exc
    return created, int(comment_id)


def _status_namespace_matches(value: object, owner: str) -> bool:
    # GitCode may return a different ASCII case for the namespace in a path.
    # Do not case-fold the repository slug or equate Unicode lookalikes.
    return isinstance(value, str) and (
        value == owner or (value.isascii() and owner.isascii() and value.lower() == owner.lower())
    )


def _status_path_matches(value: object, owner: str, repo: str) -> bool:
    if not isinstance(value, str):
        return False
    namespace, separator, slug = value.partition("/")
    return bool(separator) and slug == repo and _status_namespace_matches(namespace, owner)


def _status_url_matches(html_url: object, owner: str, repo: str) -> bool:
    # urlsplit drops some raw ASCII whitespace and controls; do not match the
    # sanitized path of an otherwise malformed URL.
    if not isinstance(html_url, str) or any(ord(char) <= 32 or ord(char) == 127 for char in html_url):
        return False
    try:
        url = urlsplit(html_url)
    except ValueError:
        return False
    if url.scheme not in ("http", "https") or url.netloc.lower() != "gitcode.com" or not url.path.startswith("/"):
        return False
    if _status_path_matches(url.path[1:].rstrip("/"), owner, repo):
        return True
    # GitCode also puts its HTTPS clone URL in html_url. Keep its raw URL
    # spelling strict and compare only the extracted namespace case-insensitively.
    return (
        url.path.endswith(".git")
        and html_url == f"https://gitcode.com{url.path}"
        and _status_path_matches(url.path[1:-4], owner, repo)
    )


def _status_base_matches(item: dict, owner: str, repo: str) -> bool:
    # A fork's head may have a different owner. Compare only advertised base identity.
    base = item.get("base")
    source = base.get("repo") if isinstance(base, dict) else None
    if not isinstance(source, dict):
        return source is None
    path = f"{owner}/{repo}"
    namespace = source.get("namespace")
    if (
        source.get("path", repo) != repo
        or (isinstance(namespace, dict) and not _status_namespace_matches(namespace.get("path", owner), owner))
        or any(
            not _status_path_matches(source.get(key, path), owner, repo)
            for key in ("full_path", "full_name", "path_with_namespace")
        )
    ):
        return False
    if "html_url" not in source:
        return True
    return _status_url_matches(source["html_url"], owner, repo)


class PullRequestAdapter:
    def __init__(
        self,
        service: PullRequestService,
        user_service: UserService | None = None,
        *,
        milestone_service: IssueService | None = None,
    ):
        self.service = service
        self.user_service = user_service
        self.milestone_service = milestone_service

    def _confirm_milestone(
        self, owner: str, repo: str, number: int, expected: int, *, snapshot: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        message = (
            f"PR #{number} may have been created or updated, but its milestone was not confirmed. "
            "Verify the PR before retrying; no write was repeated."
        )
        try:
            item = snapshot if snapshot is not None else self.service.get(owner, repo, number)
        except (GCError, ValueError) as exc:
            raise click.ClickException(message) from exc
        if not isinstance(item, dict) or milestone_number(item.get("number")) != number:
            raise click.ClickException(message)
        milestone = item.get("milestone")
        if not isinstance(milestone, dict) or milestone_number(milestone.get("number")) != expected:
            raise click.ClickException(message)
        return item

    def last_owned_comment(self, owner: str, repo: str, number: int) -> dict[str, Any] | None:
        """Select the newest ordinary comment by verified identity, not response order."""
        ownership_error = capability_message("PR_COMMENT_OWNERSHIP_UNVERIFIABLE")
        if self.user_service is None:
            raise click.ClickException(ownership_error)
        current_id, current_login = _comment_user_identity(self.user_service.current())
        comments = self.service.list_comments(owner, repo, number)
        if not isinstance(comments, list):
            raise click.ClickException("Unable to read the pull request comment history.")
        candidates: list[tuple[datetime, int, dict[str, Any]]] = []
        for comment in comments:
            if not isinstance(comment, dict):
                raise click.ClickException(ownership_error)
            if comment.get("comment_type") == "diff_comment":
                continue
            if comment.get("comment_type") != "pr_comment":
                raise click.ClickException("Unable to identify ordinary pull request comments.")
            user_id, login = _comment_user_identity(comment.get("user"))
            if current_id is not None and user_id is not None:
                owned = current_id == user_id
            elif current_login is not None and login is not None:
                owned = current_login == login
            else:
                raise click.ClickException(ownership_error)
            if not owned:
                continue
            candidates.append((*_comment_creation_key(comment), comment))
        return max(candidates, key=lambda candidate: candidate[:2])[2] if candidates else None

    def list_prs(
        self,
        owner: str,
        repo: str,
        *,
        state: str | None,
        author: str | None,
        base: str | None,
        assignee: str | None,
        draft: bool | None,
        head: str | None,
        labels: tuple[str, ...] | None,
        search: str | None,
        limit: int | None,
        merged_after: str | None = None,
        merged_before: str | None = None,
    ) -> Any:
        per_page, remaining = _normalize_limit(limit)
        if remaining == 0:
            return []
        author, assignee = resolve_me(self.user_service, author, assignee)
        params = {
            "state": state,
            "author": author,
            "base": base,
            "assignee": assignee,
            "draft": draft,
            "head": head,
            "labels": _normalize_multi_values(labels),
        }
        if search is not None:
            params["search"] = search
        if merged_after is not None:
            params["merged_after"] = merged_after
        if merged_before is not None:
            params["merged_before"] = merged_before

        items = []
        page = 1
        while True:
            page_items = self.service.list(owner, repo, **params, page=page, per_page=per_page)
            if not page_items:
                break
            items.extend(page_items)
            if remaining is not None and len(items) >= remaining:
                return items[:remaining]
            if len(page_items) < per_page:
                break
            page += 1
        return items

    def create_pr(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str | None,
        base: str,
        head: str,
        draft: bool,
        milestone: str | None,
        labels: tuple[str, ...] | None,
        reviewers: tuple[str, ...] | None,
        assignees: tuple[str, ...] | None,
        dry_run: bool,
    ) -> AdapterActionResult:
        resolved_milestone = resolve_pr_milestone(self.milestone_service, owner, repo, milestone)
        people = PRPeoplePlan(self.service, self.user_service, assignees=assignees or (), reviewers=reviewers or ())
        payload = {
            "title": title,
            "body": body,
            "base": base,
            "head": head,
            "draft": draft,
            "labels": _normalize_multi_values(labels),
            "milestone_number": resolved_milestone,
        }
        if dry_run:
            preview: dict[str, Any] = {k: v for k, v in payload.items() if v is not None}
            if people.fields:
                preview["people_operations"] = {
                    "assignees": people.add["assignees"],
                    "approval_reviewers": people.add["approval_reviewers"],
                }
            return AdapterActionResult(item=preview)
        item = self.service.create(owner, repo, **payload)
        if people.fields:
            number = milestone_number(item.get("number")) if isinstance(item, dict) else None
            if number is None:
                raise click.ClickException(
                    "PR creation may have succeeded, but its number is unavailable for people changes. "
                    "Inspect the repository before retrying; no write was repeated."
                )
            before = people.read(owner, repo, number, partial=True)
            if (
                isinstance(item, dict)
                and "id" in item
                and milestone_number(item["id"]) != milestone_number(before["id"])
            ):
                raise click.ClickException(
                    f"PR #{number} may have been created, but its creation identity was not confirmed. "
                    "Inspect the PR before retrying; no write was repeated."
                )
            item = people.apply(owner, repo, number, before)
        if resolved_milestone is not None:
            number = milestone_number(item.get("number")) if isinstance(item, dict) else None
            if number is None:
                raise click.ClickException(
                    "PR creation may have succeeded, but its number is unavailable for milestone verification. "
                    "Verify the repository before retrying; no write was repeated."
                )
            item = self._confirm_milestone(
                owner, repo, number, resolved_milestone, snapshot=item if people.fields else None
            )
        return AdapterActionResult(item=item)

    def merge_pr(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        merge_method: str,
        body: str | None,
        subject: str | None,
        admin: bool,
    ) -> dict[str, Any] | None:
        payload = {
            "merge_method": "merge" if merge_method == "squash" else merge_method,
            "squash": True if merge_method == "squash" else None,
            "description": body,
            "title": subject,
            "force_merge": True if admin else None,
        }
        return self.service.merge(owner, repo, number, **payload)

    def review_pr(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        approve: bool,  # noqa: ARG002
        body: str | None,
        comment: bool,
        request_changes: bool,
        force: bool,
    ) -> AdapterActionResult:
        if request_changes:
            raise unsupported("PR_REVIEW_REQUEST_CHANGES")
        if comment:
            item = self.service.comment(owner, repo, number, body=body or "")
            return AdapterActionResult(item=item)
        item = self.service.review(owner, repo, number, force=force)
        return AdapterActionResult(item=item)

    def edit_pr(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        title: str | None,
        body: str | None,
        add_assignee: str | None,
        add_label: str | None,
        add_reviewer: str | None,
        remove_assignee: str | None,
        remove_label: str | None,
        remove_reviewer: str | None,
        milestone: str | None,
        remove_milestone: bool,
    ) -> dict[str, Any] | None:
        if remove_milestone:
            raise unsupported("PR_EDIT_REMOVE_MILESTONE")
        resolved_milestone = resolve_pr_milestone(self.milestone_service, owner, repo, milestone)
        people = PRPeoplePlan(
            self.service,
            self.user_service,
            assignees=(add_assignee,) if add_assignee is not None else (),
            reviewers=(add_reviewer,) if add_reviewer is not None else (),
            remove_assignees=(remove_assignee,) if remove_assignee is not None else (),
            remove_reviewers=(remove_reviewer,) if remove_reviewer is not None else (),
        )
        labels = PRLabelPlan(self.service, add=add_label, remove=remove_label)
        before = people.read(owner, repo, number, partial=False) if people.fields else None
        if labels.requested:
            if before is None:
                before = labels.read(owner, repo, number, partial=False)
            else:
                labels.preflight(before, number)
        data = {
            k: v
            for k, v in {
                "title": title,
                "body": body,
                "milestone_number": resolved_milestone,
            }.items()
            if v is not None
        }
        item = self.service.update(owner, repo, number, **data) if data else before
        labels_changed = labels.apply(owner, repo, number, before) if labels.requested and before is not None else False
        if before is not None:
            if people.fields:
                item = people.apply(owner, repo, number, before, force_read=bool(data) or labels_changed)
            elif labels.requested:
                item = labels.read(owner, repo, number, partial=True) if data or labels_changed else before
        if labels.requested and before is not None:
            item = labels.confirm(number, before, item)
        if resolved_milestone is not None:
            item = self._confirm_milestone(
                owner, repo, number, resolved_milestone, snapshot=item if people.fields or labels.requested else None
            )
        return item

    def _conflict_status(self, owner: str, repo: str, page_number: int) -> list[dict]:
        # Read only the requested page; never fan out across the repository.
        page_size = 20
        page = self.service.list(owner, repo, state="open", page=page_number, per_page=page_size)
        if not isinstance(page, list) or len(page) > page_size:
            raise APIError("Cannot verify the open pull request page for conflict checks.")
        rows = []
        seen: set[int] = set()
        for item in page:
            if not isinstance(item, dict):
                raise APIError("Cannot verify a pull request in the status list.")
            number = json_number(item.get("number"))
            listed_id = json_number(item.get("id"))
            if (
                not number
                or number in seen
                or ("id" in item and not listed_id)
                or not isinstance(item.get("title"), str)
                or not item["title"].strip()
                or item.get("state") not in ("open", "opened")
                or not _status_base_matches(item, owner, repo)
            ):
                raise APIError("Cannot verify a unique, open pull request in the status list.")
            seen.add(number)
            detail = self.service.get(owner, repo, number)
            if (
                not isinstance(detail, dict)
                or json_number(detail.get("number")) != number
                or detail.get("state") not in ("open", "opened")
                or not _status_base_matches(detail, owner, repo)
                or (listed_id is not None and json_number(detail.get("id")) != listed_id)
            ):
                raise APIError(
                    f"Cannot verify open pull request #{number} against its detail; repeat the status check."
                )
            gates = detail.get("mergeable_state")
            if isinstance(gates, dict) and "merge_request_id" in gates:
                gate_id = json_number(gates["merge_request_id"])
                if not gate_id or gate_id != json_number(detail.get("id")):
                    raise APIError(f"Cannot verify the conflict check belongs to pull request #{number}.")
            passed = gates.get("conflict_passed") if isinstance(gates, dict) else None
            label = "passed" if passed is True else "not passed" if passed is False else "unknown"
            # Titles are mutable and optional in the detail response, not identity.
            title = detail.get("title")
            rows.append(
                {
                    **item,
                    "title": title if isinstance(title, str) and title.strip() else item["title"],
                    "conflict_check": label,
                }
            )
        return rows

    def status(self, owner: str, repo: str, *, conflict_status: bool = False, page: int = 1) -> AdapterActionResult:
        items = (
            self._conflict_status(owner, repo, page)
            if conflict_status
            else self.service.list(owner, repo, state="open")
        )
        return AdapterActionResult(
            items=items,
            message=capability_message("PR_STATUS_GH_SEMANTICS"),
            approximated=True,
        )
