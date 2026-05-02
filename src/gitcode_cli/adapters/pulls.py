from __future__ import annotations

from typing import Any

from ..services import PullRequestService
from .base import AdapterActionResult
from .capabilities import capability_message


def _normalize_multi_values(values: tuple[str, ...] | None) -> str | None:
    if not values:
        return None
    return ",".join(values)


class PullRequestAdapter:
    def __init__(self, service: PullRequestService):
        self.service = service

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
    ) -> Any:
        items = self.service.list(
            owner,
            repo,
            state=state,
            author=author,
            base=base,
            assignee=assignee,
            draft=draft,
            head=head,
            labels=_normalize_multi_values(labels),
            search=search,
        )
        if limit is not None:
            return items[:limit]
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
        payload = {
            "title": title,
            "body": body,
            "base": base,
            "head": head,
            "draft": draft,
            "labels": _normalize_multi_values(labels),
            "assignees": _normalize_multi_values(assignees),
            "reviewers": _normalize_multi_values(reviewers),
            "milestone": milestone,
        }
        if dry_run:
            return AdapterActionResult(item={k: v for k, v in payload.items() if v is not None})
        return AdapterActionResult(item=self.service.create(owner, repo, **payload))

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
        if comment:
            item = self.service.comment(owner, repo, number, body=body or "")
            return AdapterActionResult(
                item=item,
                message=capability_message("PR_REVIEW_COMMENT"),
                degraded=True,
            )
        if request_changes:
            item = self.service.comment(owner, repo, number, body=body or "")
            return AdapterActionResult(
                item=item,
                message=capability_message("PR_REVIEW_REQUEST_CHANGES"),
                degraded=True,
            )
        item = self.service.review(owner, repo, number, body=body, force=force)
        return AdapterActionResult(item=item)

    def edit_pr(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        title: str | None,
        body: str | None,
        base: str | None,
        add_assignee: str | None,
        add_label: str | None,
        add_reviewer: str | None,
        remove_assignee: str | None,
        remove_label: str | None,
        remove_reviewer: str | None,
        milestone: str | None,
        remove_milestone: bool,
    ) -> dict[str, Any] | None:
        data = {
            k: v
            for k, v in {
                "title": title,
                "body": body,
                "base": base,
                "assignee": add_assignee,
                "labels": add_label,
                "reviewer": add_reviewer,
                "unassignee": remove_assignee,
                "unset_labels": remove_label,
                "unset_reviewer": remove_reviewer,
                "milestone": milestone,
            }.items()
            if v is not None
        }
        if remove_milestone:
            data["milestone"] = ""
        return self.service.update(owner, repo, number, **data)

    def status(self, owner: str, repo: str) -> AdapterActionResult:
        items = self.service.list(owner, repo, state="open")
        return AdapterActionResult(
            items=items,
            message=capability_message("PR_STATUS_GH_SEMANTICS"),
            approximated=True,
        )
