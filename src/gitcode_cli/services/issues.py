from __future__ import annotations

from typing import Any

from ..client import GitCodeClient


class IssueService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues", params=params)

    def get(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues/{number}")

    def list_comments(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/issues/{number}/comments")

    def create(self, owner: str, repo: str, **data: Any) -> Any | None:
        payload: dict[str, Any] = {"repo": repo, **{k: v for k, v in data.items() if v is not None}}
        return self.client.post(f"/repos/{owner}/issues", json=payload)

    def update(self, owner: str, repo: str, number: str, **data: Any) -> Any | None:
        payload: dict[str, Any] = {"repo": repo, **{k: v for k, v in data.items() if v is not None}}
        return self.client.patch(f"/repos/{owner}/issues/{number}", json=payload)

    def comment(self, owner: str, repo: str, number: str, body: str) -> Any | None:
        return self.client.post(f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body})

    def delete(self, owner: str, repo: str, number: str) -> Any | None:
        return self.client.delete(f"/repos/{owner}/{repo}/issues/{number}")
