"""Repository services use the unchanged, credential-free client contract."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.services.repos import RepoService


class RecordingClient(GitCodeClient):
    """An old-style request override with no token or HTTP client attributes."""

    def __init__(self):
        self.calls = []
        self.result = {"ok": True}
        self.error = None

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
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.parametrize(
    ("operation", "args", "kwargs", "method", "path", "params", "body"),
    [
        ("get", ("owner", "repo"), {}, "GET", "/repos/owner/repo", None, None),
        (
            "get_branch",
            ("owner", "repo", "feature/中文%?#"),
            {},
            "GET",
            "/repos/owner/repo/branches/feature%2F%E4%B8%AD%E6%96%87%25%3F%23",
            None,
            None,
        ),
        (
            "list_branches",
            ("owner", "repo"),
            {"page": 2, "per_page": 3, "omitted": None},
            "GET",
            "/repos/owner/repo/branches",
            {"page": 2, "per_page": 3, "omitted": None},
            None,
        ),
        (
            "create_branch",
            ("owner", "repo"),
            {"branch_name": "feature/a", "refs": "base/b", "description": ""},
            "POST",
            "/repos/owner/repo/branches",
            None,
            {"branch_name": "feature/a", "refs": "base/b", "description": ""},
        ),
        (
            "get_tree",
            ("owner", "repo", "feature/a%2F"),
            {"page": 2, "recursive": 1, "file_path": "文档 #?%"},
            "GET",
            "/repos/owner/repo/git/trees/feature%2Fa%252F",
            {"page": 2, "recursive": 1, "file_path": "文档 #?%"},
            None,
        ),
        (
            "list_commits",
            ("owner", "repo"),
            {"sha": "base/%?#", "path": "a b", "per_page": 5},
            "GET",
            "/repos/owner/repo/commits",
            {"sha": "base/%?#", "path": "a b", "per_page": 5},
            None,
        ),
        (
            "get_commit",
            ("owner", "repo", "feature/a%2F"),
            {},
            "GET",
            "/repos/owner/repo/commits/feature%2Fa%252F",
            None,
            None,
        ),
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


NEW_CALLS = [
    ("list_branches", (), {"page": 2, "omitted": None}),
    ("create_branch", (), {"branch_name": "feature/a", "refs": "base/b"}),
    ("get_tree", ("feature/a",), {"page": 2, "recursive": 1}),
    ("list_commits", (), {"sha": "base/b", "per_page": 3}),
    ("get_commit", ("feature/a",), {}),
]


@pytest.mark.parametrize(("operation", "args", "kwargs"), NEW_CALLS)
@pytest.mark.parametrize("response", [None, {}, [], {"tree": [], "truncated": True}, "raw"])
def test_new_primitives_return_the_single_response_unchanged(operation, args, kwargs, response):
    client = RecordingClient()
    client.result = response
    before = dict(kwargs)
    assert getattr(RepoService(client), operation)("owner", "repo", *args, **kwargs) is response
    assert kwargs == before
    assert len(client.calls) == 1


@pytest.mark.parametrize(("operation", "args", "kwargs"), NEW_CALLS)
def test_new_primitives_propagate_the_same_transport_error_without_retry(operation, args, kwargs):
    client = RecordingClient()
    client.error = RuntimeError("transport owns error policy")
    with pytest.raises(RuntimeError) as raised:
        getattr(RepoService(client), operation)("owner", "repo", *args, **kwargs)
    assert raised.value is client.error
    assert len(client.calls) == 1


@pytest.mark.parametrize(("operation", "suffix"), [("get_tree", "git/trees"), ("get_commit", "commits")])
@pytest.mark.parametrize("ref", ["feature/a", "中文 space?#%", "%2F", "%2e%2e", "v1.0", "ref\u0085\u009f"])
def test_new_reference_segments_encode_decoded_text_once(operation, suffix, ref):
    client = RecordingClient()
    getattr(RepoService(client), operation)("owner", "repo", ref)
    assert client.calls[0][1] == f"/repos/owner/repo/{suffix}/" + quote(ref, safe="")


@pytest.mark.parametrize("operation", ["get_tree", "get_commit"])
@pytest.mark.parametrize(
    "ref",
    [
        "",
        ".",
        "..",
        "a/../b",
        "a/./b",
        "/leading",
        "trailing/",
        "a//b",
        "bad\x00ref",
        "bad\x7fref",
        "bad\ud800ref",
        "a\\b",
        None,
        False,
    ],
)
def test_invalid_new_reference_segments_fail_before_transport(operation, ref):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(RepoService(client), operation)("owner", "repo", ref)
    assert client.calls == []


@pytest.mark.parametrize(("operation", "args", "kwargs"), NEW_CALLS)
@pytest.mark.parametrize(
    ("owner", "repo"),
    [
        ("", "repo"),
        ("owner", "."),
        ("..", "repo"),
        ("a/b", "repo"),
        ("owner", "a/b"),
        ("a\\b", "repo"),
        ("owner", "a\x7fb"),
        ("\ud800", "repo"),
        ("owner", None),
    ],
)
def test_new_primitives_reject_invalid_repository_segments_before_transport(operation, args, kwargs, owner, repo):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(RepoService(client), operation)(owner, repo, *args, **kwargs)
    assert client.calls == []


@pytest.mark.parametrize(("operation", "args", "kwargs"), NEW_CALLS)
def test_new_primitives_encode_owner_and_repo_without_decoding_percent_sequences(operation, args, kwargs):
    client = RecordingClient()
    getattr(RepoService(client), operation)("team space", "项目%2F", *args, **kwargs)
    assert client.calls[0][1].startswith("/repos/team%20space/%E9%A1%B9%E7%9B%AE%252F/")


@pytest.mark.parametrize("field", ["branch_name", "refs"])
def test_create_branch_requires_both_explicit_fields_without_lookup(field):
    client = RecordingClient()
    kwargs = {"branch_name": "feature/a", "refs": "base/b"}
    del kwargs[field]
    with pytest.raises(TypeError):
        RepoService(client).create_branch("owner", "repo", **kwargs)
    assert client.calls == []


@pytest.mark.parametrize("field", ["branch_name", "refs"])
@pytest.mark.parametrize("value", ["", "  ", "\t", "ref\n", "ref\x7f", "\ud800", None, False])
def test_create_branch_refuses_blank_or_invalid_text_before_transport(field, value):
    client = RecordingClient()
    with pytest.raises(ValueError):
        RepoService(client).create_branch("owner", "repo", **{"branch_name": "new", "refs": "old", field: value})
    assert client.calls == []


@pytest.mark.parametrize("description", [None, "", "说明"])
def test_create_branch_preserves_literal_body_text_and_omits_only_none_description(description):
    client = RecordingClient()
    kwargs = {"branch_name": " feature/中文%?# ", "refs": " base/%2F ", "description": description}
    RepoService(client).create_branch("owner", "repo", **kwargs)
    expected = {key: value for key, value in kwargs.items() if value is not None}
    assert client.calls == [("POST", "/repos/owner/repo/branches", None, expected, "application/json", "json")]
