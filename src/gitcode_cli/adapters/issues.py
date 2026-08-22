from __future__ import annotations

from typing import Any

import click

from ..errors import APIError
from ..services import IssueService, UserService
from .base import AdapterActionResult
from .capabilities import capability_message


def _normalize_multi_values(values: tuple[str, ...] | None) -> str | None:
    if not values:
        return None
    return ",".join(values)


def _normalize_labels(labels: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if not labels:
        return None
    normalized = tuple(label.strip() for label in labels if label.strip())
    return normalized or None


def _extract_label_names(issue: dict[str, Any] | None) -> list[str]:
    labels = issue.get("labels") if isinstance(issue, dict) else None
    if not labels:
        return []
    if isinstance(labels, str):
        return [part.strip() for part in labels.split(",") if part.strip()]

    names: list[str] = []
    if isinstance(labels, list):
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name") or label.get("title")
                if name:
                    names.append(str(name))
            elif label:
                names.append(str(label))
    return names


def _extract_assignee_names(issue: dict[str, Any] | None) -> list[str]:
    assignees = issue.get("assignees") if isinstance(issue, dict) else None
    if isinstance(assignees, str):
        return [part.strip() for part in assignees.split(",") if part.strip()]
    if isinstance(assignees, list):
        names: list[str] = []
        for assignee in assignees:
            if isinstance(assignee, dict):
                name = _extract_login(assignee)
                if name:
                    names.append(name)
            elif assignee:
                names.append(str(assignee))
        return names

    assignee = issue.get("assignee") if isinstance(issue, dict) else None
    if isinstance(assignee, str):
        return [part.strip() for part in assignee.split(",") if part.strip()]
    if isinstance(assignee, dict):
        name = _extract_login(assignee)
        return [name] if name else []
    return []


def _matches_all_labels(issue: dict[str, Any], labels: tuple[str, ...] | None) -> bool:
    if not labels or len(labels) < 2:
        return True
    actual = {label.lower() for label in _extract_label_names(issue)}
    return all(label.lower() in actual for label in labels)


def _extract_login(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("login", "username", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    user = data.get("user")
    if isinstance(user, dict):
        return _extract_login(user)
    author = data.get("author")
    if isinstance(author, dict):
        return _extract_login(author)
    return None


def _as_list(items: Any) -> list[Any]:
    return items if isinstance(items, list) else []


def _extract_label_options(items: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _resolve_milestone_number(items: list[Any], milestone: str | None) -> int | None:
    if milestone is None:
        return None
    value = milestone.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    matches: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        number = item.get("number")
        if title != value:
            continue
        if isinstance(number, int):
            matches.append(number)
        elif isinstance(number, str) and number.isdigit():
            matches.append(int(number))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise click.ClickException(f"could not resolve milestone: '{value}' matched multiple milestones")
    raise click.ClickException(f"could not resolve milestone: '{value}' not found")


class IssueAdapter:
    def __init__(self, service: IssueService, user_service: UserService | None = None):
        self.service = service
        self.user_service = user_service

    def _list_all_labels(self, owner: str, repo: str) -> list[Any]:
        items: list[Any] = []
        page = 1
        while True:
            page_items = _as_list(self.service.list_labels(owner, repo, page=page, per_page=100))
            items.extend(page_items)
            if len(page_items) < 100:
                return items
            page += 1

    def _list_all_milestones(self, owner: str, repo: str) -> list[Any]:
        items: list[Any] = []
        page = 1
        while True:
            page_items = _as_list(self.service.list_milestones(owner, repo, state="all", page=page, per_page=100))
            items.extend(page_items)
            if len(page_items) < 100:
                return items
            page += 1

    def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str | None,
        labels: tuple[str, ...] | None,
        author: str | None,
        assignee: str | None,
        milestone: str | None,
        mention: str | None,
        search: str | None,
        limit: int | None,
    ) -> Any:
        if author == "@me":
            if self.user_service is None:
                raise click.ClickException("failed to resolve @me: current user lookup is unavailable")
            current_login = _extract_login(self.user_service.current())
            if not current_login:
                raise click.ClickException("failed to resolve @me: current user has no login")
            author = current_login
        params = {
            "state": state,
            "labels": _normalize_multi_values(labels),
            "creator": author,
            "assignee": assignee,
            "milestone": milestone,
            "mention": mention,
            "search": search,
        }
        needs_and_filter = bool(labels) and len(labels) > 1
        per_page = 100 if limit is None else min(limit, 100)
        items: list[Any] = []
        page = 1
        while True:
            page_items = _as_list(self.service.list(owner, repo, **params, page=page, per_page=per_page))
            if not page_items:
                break
            items.extend(page_items)
            if len(page_items) < per_page:
                break
            if limit is not None:
                if needs_and_filter:
                    matched = sum(1 for item in items if _matches_all_labels(item, labels))
                else:
                    matched = len(items)
                if matched >= limit:
                    break
            page += 1
        if needs_and_filter:
            items = [item for item in items if _matches_all_labels(item, labels)]
        if limit is not None:
            return items[:limit]
        return items

    def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str | None,
        assignee: str | None,
        labels: tuple[str, ...] | None,
        milestone: str | None,
    ) -> dict[str, Any] | None:
        normalized_labels = _normalize_labels(labels)
        if normalized_labels:
            available_labels = _extract_label_options(self._list_all_labels(owner, repo))
            for label in normalized_labels:
                if label not in available_labels:
                    raise click.ClickException(f"could not add label: '{label}' not found")
        milestone_number = None
        if milestone is not None:
            milestones = []
            if not milestone.strip().isdigit():
                milestones = self._list_all_milestones(owner, repo)
            milestone_number = _resolve_milestone_number(milestones, milestone)
        return self.service.create(
            owner,
            repo,
            title=title,
            body=body,
            assignee=assignee,
            labels=_normalize_multi_values(normalized_labels),
            milestone=milestone_number,
        )

    def close_issue(
        self,
        owner: str,
        repo: str,
        number: str,
        *,
        comment: str | None,
        reason: str | None,
    ) -> AdapterActionResult:
        current = self.service.get(owner, repo, number)
        if current and current.get("state") == "closed":
            if comment:
                self.service.comment(owner, repo, number, comment)
                return AdapterActionResult(item=current, message="already_closed_commented")
            return AdapterActionResult(item=current, message="already_closed")
        if comment:
            self.service.comment(owner, repo, number, comment)
        payload: dict[str, Any] = {"state": "close"}
        if reason:
            payload["state_reason"] = reason
        item = self.service.update(owner, repo, number, **payload)
        return AdapterActionResult(item=item, message="closed")

    def comment_issue(self, owner: str, repo: str, number: str, *, body: str) -> dict[str, Any] | None:
        return self.service.comment(owner, repo, number, body)

    def manage_comment_history(
        self,
        owner: str,
        repo: str,
        number: str,
        *,
        body: str | None,
        delete_last: bool,
        create_if_none: bool,
    ) -> AdapterActionResult:
        comment = self._find_last_owned_comment(owner, repo, number)
        if delete_last:
            if comment is None:
                raise click.ClickException(capability_message("ISSUE_COMMENT_LAST_NOT_FOUND"))
            self.service.delete_comment(owner, repo, comment["id"])
            return AdapterActionResult(item=comment, message="deleted")
        if comment is None:
            if create_if_none:
                item = self.service.comment(owner, repo, number, body or "")
                return AdapterActionResult(item=item, message="created")
            raise click.ClickException(capability_message("ISSUE_COMMENT_LAST_NOT_FOUND"))
        item = self.service.update_comment(owner, repo, comment["id"], body or "")
        return AdapterActionResult(item=item, message="edited")

    def _find_last_owned_comment(self, owner: str, repo: str, number: str) -> dict[str, Any] | None:
        if self.user_service is None:
            raise click.ClickException(capability_message("ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE"))
        try:
            current_user = self.user_service.current()
        except APIError as exc:
            raise click.ClickException(capability_message("ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE")) from exc
        current_login = _extract_login(current_user)
        if not current_login:
            raise click.ClickException(capability_message("ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE"))
        comments = self.service.list_comments(owner, repo, number) or []
        for comment in reversed(comments):
            if not isinstance(comment, dict):
                continue
            if _extract_login(comment) == current_login:
                return comment
        return None

    def reopen_issue(self, owner: str, repo: str, number: str, *, comment: str | None = None) -> AdapterActionResult:
        current = self.service.get(owner, repo, number)
        if current and current.get("state") == "open":
            return AdapterActionResult(item=current, message="already_open")
        item = self.service.update(owner, repo, number, state="reopen")
        if comment:
            self.service.comment(owner, repo, number, comment)
        return AdapterActionResult(item=item, message="reopened")

    def delete_issue(self, owner: str, repo: str, number: str) -> AdapterActionResult:
        item = self.service.delete(owner, repo, number)
        return AdapterActionResult(item=item, message="deleted")

    def edit_issue(
        self,
        owner: str,
        repo: str,
        number: str,
        *,
        title: str | None,
        body: str | None,
        add_assignee: str | None,
        add_labels: tuple[str, ...] | None,
        remove_assignee: str | None,
        remove_labels: tuple[str, ...] | None,
        milestone: int | None,
        remove_milestone: bool,
    ) -> dict[str, Any] | None:
        data: dict[str, Any] = {k: v for k, v in {"title": title, "body": body}.items() if v is not None}

        if add_assignee is not None:
            data["assignee"] = add_assignee
        if remove_assignee is not None:
            current = self.service.get(owner, repo, number)
            remaining = [name for name in _extract_assignee_names(current) if name != remove_assignee]
            data["assignee"] = ",".join(remaining)

        if add_labels or remove_labels:
            current = self.service.get(owner, repo, number)
            existing = _extract_label_names(current)
            removed = {label.strip() for label in remove_labels or () if label.strip()}
            merged: list[str] = []
            seen: set[str] = set()
            for label in [*existing, *list(add_labels or ())]:
                normalized = label.strip()
                if normalized and normalized not in removed and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
            data["labels"] = ",".join(merged)

        if milestone is not None:
            data["milestone"] = milestone
        if remove_milestone:
            data["milestone"] = 0
        return self.service.update(owner, repo, number, **data)

    def status(self, owner: str, repo: str) -> AdapterActionResult:
        if self.user_service is None:
            raise click.ClickException("failed to resolve current user: current user lookup is unavailable")
        current_login = _extract_login(self.user_service.current())
        if not current_login:
            raise click.ClickException("failed to resolve current user: current user has no login")
        assigned = self.service.list_user_issues(filter="assigned", state="open") or []
        created = self.service.list_user_issues(filter="created", state="open") or []
        mentioned = self.service.list(owner, repo, state="open", mention=current_login) or []
        return AdapterActionResult(
            item={"assigned": assigned, "mentioned": mentioned, "createdBy": created},
            message=capability_message("ISSUE_STATUS_GH_SEMANTICS"),
            approximated=True,
        )

    def develop(self, owner: str, repo: str, number: str, *, base: str | None, name: str | None) -> AdapterActionResult:  # noqa: ARG002
        return AdapterActionResult(
            message=f"Opening issue #{number} in the browser instead.",
            warning="Note: 'issue develop' does not create a local branch on GitCode.",
        )
