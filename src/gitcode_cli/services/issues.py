from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..client import GitCodeClient
from ._pagination import collect_pages


class IssueService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues", params=params)

    def list_user_issues(self, **params: Any) -> Any | None:
        return self.client.get("/user/issues", params=params)

    def list_labels(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/labels", params=params)

    def list_milestones(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/milestones", params=params)

    def get(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues/{number}")

    def list_comments(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues/{number}/comments")

    def list_all_comments(self, owner: str, repo: str, number: str) -> list[Any]:
        """Collect complete comments or raise; leave the legacy single-page method unchanged."""
        return collect_pages(self.client, f"/repos/{owner}/{repo}/issues/{number}/comments")

    def remove_label(self, owner: str, repo: str, number: str, name: str) -> Any | None:
        """Remove one label without replacing the Issue's other labels."""
        if not name or "," in name:
            raise ValueError("Provide exactly one nonempty label name")
        return self.client.delete(f"/repos/{owner}/{repo}/issues/{number}/labels/{quote(name, safe='')}")

    def create(self, owner: str, repo: str, **data: Any) -> Any | None:
        payload: dict[str, Any] = {"repo": repo, **{k: v for k, v in data.items() if v is not None}}
        return self.client.post(f"/repos/{owner}/issues", json=payload)

    def update(self, owner: str, repo: str, number: str, **data: Any) -> Any | None:
        payload: dict[str, Any] = {"repo": repo, **{k: v for k, v in data.items() if v is not None}}
        return self.client.patch(f"/repos/{owner}/issues/{number}", json=payload)

    def delete(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.delete(f"/repos/{owner}/{repo}/issues/{number}")

    def comment(self, owner: str, repo: str, number: str, body: str) -> Any | None:
        return self.client.post(f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body})

    def update_comment(self, owner: str, repo: str, comment_id: int | str, body: str) -> Any | None:
        return self.client.patch(f"/repos/{owner}/{repo}/issues/comments/{comment_id}", json={"body": body})

    def delete_comment(self, owner: str, repo: str, comment_id: int | str) -> Any | None:
        return self.client.delete(f"/repos/{owner}/{repo}/issues/comments/{comment_id}")
