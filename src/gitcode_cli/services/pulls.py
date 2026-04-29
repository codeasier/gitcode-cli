from __future__ import annotations

from typing import Any

from ..client import GitCodeClient


class PullRequestService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/pulls", params=params)

    def get(self, owner: str, repo: str, number: int) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{number}")

    def create(self, owner: str, repo: str, **data: Any) -> Any | None:
        return self.client.post(f"/repos/{owner}/{repo}/pulls", json={k: v for k, v in data.items() if v is not None})

    def update(self, owner: str, repo: str, number: int, **data: Any) -> Any | None:
        return self.client.patch(
            f"/repos/{owner}/{repo}/pulls/{number}", json={k: v for k, v in data.items() if v is not None}
        )

    def merge(self, owner: str, repo: str, number: int, **data: Any) -> Any | None:
        return self.client.put(
            f"/repos/{owner}/{repo}/pulls/{number}/merge", json={k: v for k, v in data.items() if v is not None}
        )

    def comment(
        self, owner: str, repo: str, number: int, body: str, path: str | None = None, position: int | None = None
    ) -> Any | None:
        payload: dict[str, Any] = {"body": body, "path": path, "position": position}
        return self.client.post(
            f"/repos/{owner}/{repo}/pulls/{number}/comments", json={k: v for k, v in payload.items() if v is not None}
        )

    def review(self, owner: str, repo: str, number: int, body: str | None = None, force: bool = False) -> Any | None:
        payload = {"body": body, "force": force}
        filtered_payload = {k: v for k, v in payload.items() if v is not None}
        return self.client.post(f"/repos/{owner}/{repo}/pulls/{number}/review", json=filtered_payload)

    def list_comments(self, owner: str, repo: str, number: int) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{number}/comments")

    def diff(self, owner: str, repo: str, number: int) -> str:
        response = self.client.request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}/diff",
            accept="text/plain",
            response_format="text",
        )
        return response or ""
