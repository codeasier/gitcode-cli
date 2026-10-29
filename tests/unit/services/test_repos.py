"""Repository services use the unchanged, credential-free client contract."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.services.repos import RepoService


class RecordingClient(GitCodeClient):
    """An old-style request override with no token or HTTP client attributes."""

    def __init__(self):
        self.calls = []

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        response_format: Literal["json", "text"] = "json",
    ) -> Any:
        self.calls.append((method, path, params, json, accept, response_format))
        return {"ok": True}


@pytest.mark.parametrize(
    ("operation", "args", "kwargs", "method", "path", "params", "body"),
    [
        ("get", ("owner", "repo"), {}, "GET", "/repos/owner/repo", None, None),
        (
            "contents",
            ("owner", "repo", "docs/README.md"),
            {"ref": "main"},
            "GET",
            "/repos/owner/repo/contents/docs/README.md",
            {"ref": "main"},
            None,
        ),
        ("list_own", (), {"page": 2}, "GET", "/user/repos", {"page": 2}, None),
        ("list_user", ("owner",), {"per_page": 5}, "GET", "/users/owner/repos", {"per_page": 5}, None),
        ("list_org", ("org",), {"page": 1}, "GET", "/orgs/org/repos", {"page": 1}, None),
        ("create_personal", (), {"name": "repo"}, "POST", "/user/repos", None, {"name": "repo"}),
        ("create_org", ("org",), {"name": "repo"}, "POST", "/orgs/org/repos", None, {"name": "repo"}),
        ("update", ("owner", "repo"), {"private": True}, "PATCH", "/repos/owner/repo", None, {"private": True}),
        ("delete", ("owner", "repo"), {}, "DELETE", "/repos/owner/repo", None, None),
        ("fork", ("owner", "repo"), {"org": None}, "POST", "/repos/owner/repo/forks", None, None),
        ("fork", ("owner", "repo"), {"org": "org"}, "POST", "/repos/owner/repo/forks", None, {"org": "org"}),
        ("sync", ("owner", "repo"), {}, "PUT", "/repos/owner/repo/sync_repo", None, None),
    ],
)
def test_repo_service_preserves_request_override_contract(operation, args, kwargs, method, path, params, body):
    client = RecordingClient()
    service = RepoService(client)

    assert getattr(service, operation)(*args, **kwargs) == {"ok": True}
    assert client.calls == [(method, path, params, body, "application/json", "json")]
    assert not hasattr(client, "token")
