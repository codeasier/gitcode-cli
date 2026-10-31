"""Wire contracts for request shapes already used by MCP, not live API acceptance."""

from __future__ import annotations

import json

import httpx
import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError, NetworkError
from gitcode_cli.services.repos import RepoService

TOKEN = "synthetic-repository-contract-token"


@pytest.fixture
def wire(monkeypatch):
    requests = []
    outcomes = []

    def handler(request):
        requests.append(request)
        outcome = outcomes.pop(0) if outcomes else httpx.Response(200, json={"tree": [], "truncated": True})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    original_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(**kwargs, transport=transport, trust_env=False)
    )
    client = GitCodeClient(TOKEN)
    try:
        yield RepoService(client), requests, outcomes
    finally:
        client.close()


@pytest.mark.parametrize(
    ("operation", "args", "kwargs", "method", "suffix", "query", "body"),
    [
        (
            "list_branches",
            (),
            {"page": 2, "per_page": 3, "omitted": None},
            "GET",
            "branches",
            {"page": "2", "per_page": "3"},
            None,
        ),
        (
            "create_branch",
            (),
            {"branch_name": "feature/中文%?#", "refs": "base/%2F", "description": ""},
            "POST",
            "branches",
            {},
            {"branch_name": "feature/中文%?#", "refs": "base/%2F", "description": ""},
        ),
        (
            "get_tree",
            ("feature/中文 ?#%2F",),
            {"recursive": 1, "page": 2, "per_page": 3, "file_path": "文档 #?%"},
            "GET",
            "git/trees/feature%2F%E4%B8%AD%E6%96%87%20%3F%23%252F",
            {"recursive": "1", "page": "2", "per_page": "3", "file_path": "文档 #?%"},
            None,
        ),
        (
            "list_commits",
            (),
            {"sha": "feature/中文 ?#%2F", "path": "文档 #?%", "page": 2, "per_page": 3},
            "GET",
            "commits",
            {"sha": "feature/中文 ?#%2F", "path": "文档 #?%", "page": "2", "per_page": "3"},
            None,
        ),
        (
            "get_commit",
            ("feature/中文 ?#%2F",),
            {},
            "GET",
            "commits/feature%2F%E4%B8%AD%E6%96%87%20%3F%23%252F",
            {},
            None,
        ),
        (
            "get_branch",
            ("feature/中文 ?#%2F",),
            {},
            "GET",
            "branches/feature%2F%E4%B8%AD%E6%96%87%20%3F%23%252F",
            {},
            None,
        ),
    ],
)
def test_real_cli_transport_preserves_single_request_shape_and_owns_auth(
    wire, operation, args, kwargs, method, suffix, query, body
):
    service, requests, _ = wire
    assert getattr(service, operation)("owner", "repo", *args, **kwargs) == {"tree": [], "truncated": True}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == method
    assert request.url.scheme == "https"
    assert request.url.host == "api.gitcode.com"
    assert request.url.raw_path.split(b"?", 1)[0] == f"/api/v5/repos/owner/repo/{suffix}".encode("ascii")
    assert dict(request.url.params) == {"access_token": TOKEN, **query}
    assert request.headers["Accept"] == "application/json"
    assert "private-token" not in request.headers
    assert "Authorization" not in request.headers
    if body is None:
        assert request.content == b""
    else:
        assert json.loads(request.content) == body


@pytest.mark.parametrize("operation", ["get_tree", "get_commit"])
@pytest.mark.parametrize(
    "ref",
    ["", ".", "..", "feature/../x", "a/./b", "/leading", "trailing/", "a//b", "bad\\ref", "bad\x00ref", "bad\ud800ref"],
)
def test_new_segment_validation_prevents_urljoin_normalization_before_real_transport(wire, operation, ref):
    service, requests, _ = wire
    with pytest.raises(ValueError):
        getattr(service, operation)("owner", "repo", ref)
    assert requests == []


@pytest.mark.parametrize(
    ("operation", "args", "kwargs"),
    [
        ("list_branches", (), {}),
        ("create_branch", (), {"branch_name": "new", "refs": "main"}),
        ("get_tree", ("main",), {}),
        ("list_commits", (), {}),
        ("get_commit", ("main",), {}),
    ],
)
@pytest.mark.parametrize("outcome", ["rejected", "timeout"])
def test_new_primitives_keep_cli_error_policy_without_lookup_or_retry(wire, operation, args, kwargs, outcome):
    service, requests, outcomes = wire
    outcomes.append(
        httpx.Response(422, json={"message": "rejected"}) if outcome == "rejected" else httpx.ReadTimeout("slow")
    )
    with pytest.raises(APIError if outcome == "rejected" else NetworkError) as raised:
        getattr(service, operation)("owner", "repo", *args, **kwargs)
    assert len(requests) == 1
    if outcome == "rejected":
        assert raised.value.status_code == 422
        suffix = " Verify the remote state before retrying this write." if operation == "create_branch" else ""
        assert str(raised.value) == "rejected" + suffix
    else:
        assert "Request timed out" in str(raised.value)
    if operation == "create_branch":
        assert "Verify the remote state before retrying this write." in str(raised.value)


def test_existing_repository_get_still_uses_the_cli_private_token_allowlist(wire):
    service, requests, _ = wire
    service.get("owner", "repo")
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v5/repos/owner/repo"
    assert requests[0].headers["private-token"] == TOKEN
    assert dict(requests[0].url.params) == {"access_token": TOKEN}
