from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ..errors import APIError


class PullRequestService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list(self, owner: str, repo: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/pulls", params=params)

    def get(self, owner: str, repo: str, number: int) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{number}")

    def _paginate(self, path: str) -> Any | None:
        per_page = 100
        page = 1
        items: list[Any] = []
        previous: list[Any] | None = None
        while True:
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            result = self.client.get(path, params=params)
            if not isinstance(result, list):
                if result is None and page == 1 and not items:
                    return None
                raise APIError(f"Unexpected pagination response for {path} page {page}")
            if previous is not None and result == previous:
                raise APIError(f"Repeated pagination response for {path} page {page}")
            items.extend(result)
            if len(result) < per_page:
                return items
            if page >= 100:
                raise APIError(f"Pagination limit exceeded for {path}")
            previous = result
            page += 1

    def list_issues(self, owner: str, repo: str, number: int) -> Any | None:
        return self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/issues")

    def list_files(self, owner: str, repo: str, number: int) -> Any | None:
        return self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/files")

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
        return self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/comments")

    def diff(self, owner: str, repo: str, number: int) -> str:
        response = self.client.request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}/diff",
            accept="text/plain",
            response_format="text",
        )
        return response or ""
