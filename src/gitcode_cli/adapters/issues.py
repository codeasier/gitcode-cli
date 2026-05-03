from __future__ import annotations

from typing import Any

from ..services import IssueService
from .base import AdapterActionResult
from .capabilities import capability_message, unsupported


def _normalize_multi_values(values: tuple[str, ...] | None) -> str | None:
    if not values:
        return None
    return ",".join(values)


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


class IssueAdapter:
    def __init__(self, service: IssueService):
        self.service = service

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
        items = self.service.list(
            owner,
            repo,
            state=state,
            labels=_normalize_multi_values(labels),
            creator=author,
            assignee=assignee,
            milestone=milestone,
            mention=mention,
            search=search,
        )
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
        return self.service.create(
            owner,
            repo,
            title=title,
            body=body,
            assignee=assignee,
            labels=_normalize_multi_values(labels),
            milestone=milestone,
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

    def reopen_issue(self, owner: str, repo: str, number: str) -> AdapterActionResult:
        current = self.service.get(owner, repo, number)
        if current and current.get("state") == "open":
            return AdapterActionResult(item=current, message="already_open")
        item = self.service.update(owner, repo, number, state="reopen")
        return AdapterActionResult(item=item, message="reopened")

    def delete_issue(self, owner: str, repo: str, number: str) -> AdapterActionResult:  # noqa: ARG002
        raise unsupported("ISSUE_DELETE")

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
        milestone: str | None,
        remove_milestone: bool,
    ) -> dict[str, Any] | None:
        data = {k: v for k, v in {"title": title, "body": body}.items() if v is not None}

        if add_assignee is not None:
            data["assignee"] = add_assignee

        if add_labels:
            current = self.service.get(owner, repo, number)
            existing = _extract_label_names(current)
            merged: list[str] = []
            seen: set[str] = set()
            for label in [*existing, *list(add_labels)]:
                normalized = label.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
            data["labels"] = ",".join(merged)

        if milestone is not None:
            data["milestone"] = milestone
        if remove_milestone:
            data["milestone"] = ""
        return self.service.update(owner, repo, number, **data)

    def status(self, owner: str, repo: str) -> AdapterActionResult:
        items = self.service.list(owner, repo, state="open")
        return AdapterActionResult(
            items=items,
            message=capability_message("ISSUE_STATUS_GH_SEMANTICS"),
            approximated=True,
        )

    def develop(self, owner: str, repo: str, number: str, *, base: str | None, name: str | None) -> AdapterActionResult:  # noqa: ARG002
        if base is not None:
            raise unsupported("ISSUE_DEVELOP_BASE")
        if name is not None:
            raise unsupported("ISSUE_DEVELOP_NAME")
        return AdapterActionResult(
            message=f"Opening issue #{number} in the browser instead.",
            warning="Note: 'issue develop' does not create a local branch on GitCode.",
        )
