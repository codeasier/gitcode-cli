from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..client import GitCodeClient
from .files import FileService


def _literal_text(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Use nonempty UTF-8 text without ASCII C0/DEL controls.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Use valid UTF-8 text without unpaired surrogates.") from None
    return value


def _segment(value: str) -> str:
    value = _literal_text(value)
    if any(part in {"", ".", ".."} for part in value.split("/")) or "\\" in value:
        raise ValueError("Use a resource name without empty/dot components or backslashes.")
    return quote(value, safe="")


def _repository_path(owner: str, repo: str) -> str:
    encoded_owner, encoded_repo = _segment(owner), _segment(repo)
    if "/" in owner or "/" in repo:
        raise ValueError("Owner and repository must each be one path segment.")
    return f"/repos/{encoded_owner}/{encoded_repo}"


class RepoService:
    """Thin wrappers over the GitCode v5 repository endpoints.

    Authentication belongs to the supplied transport. The CLI adds its
    repository-specific header there; alternate clients retain their own policy.
    """

    def __init__(self, client: GitCodeClient):
        self.client = client

    def get(self, owner: str, repo: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}")

    def get_branch(self, owner: str, repo: str, branch: str) -> Any | None:
        return self.client.get(f"/repos/{owner}/{repo}/branches/{quote(branch, safe='')}")

    def list_branches(self, owner: str, repo: str, **params: Any) -> Any | None:
        """Read one branch page; query encoding and pagination policy stay with the caller/client."""
        return self.client.get(f"{_repository_path(owner, repo)}/branches", params=params)

    def create_branch(
        self, owner: str, repo: str, *, branch_name: str, refs: str, description: str | None = None
    ) -> Any | None:
        """Create once from an explicit source, without a default-branch lookup or retry."""
        branch_name, refs = _literal_text(branch_name), _literal_text(refs)
        if not branch_name.strip() or not refs.strip():
            raise ValueError("Provide an explicit nonblank branch_name and refs.")
        payload = {"branch_name": branch_name, "refs": refs}
        if description is not None:
            payload["description"] = description
        return self.client.post(f"{_repository_path(owner, repo)}/branches", json=payload)

    def get_tree(self, owner: str, repo: str, sha: str, **params: Any) -> Any | None:
        """Read one tree response with a decoded reference encoded as one segment."""
        return self.client.get(f"{_repository_path(owner, repo)}/git/trees/{_segment(sha)}", params=params)

    def list_commits(self, owner: str, repo: str, **params: Any) -> Any | None:
        """Read one commit page, preserving literal query values and the upstream result."""
        return self.client.get(f"{_repository_path(owner, repo)}/commits", params=params)

    def get_commit(self, owner: str, repo: str, sha: str) -> Any | None:
        """Read one commit; a literal percent sequence is data, not pre-encoded input."""
        return self.client.get(f"{_repository_path(owner, repo)}/commits/{_segment(sha)}")

    def contents(self, owner: str, repo: str, path: str, **params: Any) -> Any | None:
        """Read a decoded relative path through the canonical Contents service."""
        return FileService(self.client).get(owner, repo, path, **params)

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
