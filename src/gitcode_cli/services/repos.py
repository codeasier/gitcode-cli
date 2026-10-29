from __future__ import annotations

from typing import Any

from ..client import GitCodeClient


class RepoService:
    """Thin wrappers over the GitCode v5 repository endpoints.

    Authentication belongs to the supplied transport. The CLI adds its
    repository-specific header there; alternate clients retain their own policy.
    """

    def __init__(self, client: GitCodeClient):
        self.client = client

    def get(self, owner: str, repo: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}")

    def contents(self, owner: str, repo: str, path: str, **params: Any) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

    def list_own(self, **params: Any) -> Any | None:
        return self.client.get("/user/repos", params=params)

    def list_user(self, owner: str, **params: Any) -> Any | None:
        return self.client.get(f"/users/{owner}/repos", params=params)

    def list_org(self, org: str, **params: Any) -> Any | None:
        return self.client.get(f"/orgs/{org}/repos", params=params)

    def create_personal(self, **data: Any) -> Any | None:
        return self.client.post("/user/repos", json=data)

    def create_org(self, org: str, **data: Any) -> Any | None:
        return self.client.post(f"/orgs/{org}/repos", json=data)

    def update(self, owner: str, repo: str, **data: Any) -> Any | None:
        return self.client.patch(f"/repos/{owner}/{repo}", json=data)

    def delete(self, owner: str, repo: str) -> Any | None:
        return self.client.delete(f"/repos/{owner}/{repo}")

    def fork(self, owner: str, repo: str, **data: Any) -> Any | None:
        payload = {k: v for k, v in data.items() if v is not None}
        return self.client.post(f"/repos/{owner}/{repo}/forks", json=payload or None)

    def sync(self, owner: str, repo: str) -> Any | None:
        return self.client.put(f"/repos/{owner}/{repo}/sync_repo")
