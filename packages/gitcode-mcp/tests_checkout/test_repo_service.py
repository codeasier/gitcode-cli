"""Unreleased producer contracts: selected only after installing the CLI checkout.

These methods are absent from published pygitcode 0.1.7. Do not move this module
to tests/ or tests_source/, which also run against actual published artifacts.
Production tools do not delegate to these methods yet.
"""

import json
from urllib.parse import quote

import httpx
import pytest
from gitcode_cli.services.repos import RepoService

from gitcode_mcp.api import GitCodeAPI, GitCodeError

TOKEN = "synthetic-repository-service-token"
REF = "feature/中文 space"
OPERATIONS = ["list_branches", "create_branch", "get_tree", "list_commits", "get_commit"]


def arguments(operation):
    if operation == "create_branch":
        return (), {"branch_name": REF, "refs": "base/%?#", "description": ""}
    if operation == "get_tree":
        return (REF,), {"recursive": 1, "file_path": "文档 #?%", "page": 2, "per_page": 3}
    if operation == "get_commit":
        return (REF,), {}
    params = {"page": 2, "per_page": 3, "omitted": None}
    if operation == "list_commits":
        params.update(sha="feature/中文+%?#", path="文档 #?%")
    return (), params


@pytest.mark.parametrize("operation", OPERATIONS)
def test_unreleased_service_uses_the_real_bounded_bearer_transport_once(operation, monkeypatch):
    requests = []
    options = []
    original_client = httpx.Client

    def client(**kwargs):
        options.append(kwargs)
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"echo": TOKEN, "tree": [], "truncated": True})

    args, kwargs = arguments(operation)
    with GitCodeAPI(TOKEN, timeout=7.5, transport=httpx.MockTransport(handler)) as api:
        result = getattr(RepoService(api), operation)("team", "project", *args, **kwargs)

    assert len(requests) == len(options) == 1
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert options[0]["timeout"] == 7.5
    request = requests[0]
    assert request.method == ("POST" if operation == "create_branch" else "GET")
    suffix = {
        "list_branches": "branches",
        "create_branch": "branches",
        "get_tree": "git/trees/" + quote(REF, safe=""),
        "list_commits": "commits",
        "get_commit": "commits/" + quote(REF, safe=""),
    }[operation]
    assert request.url.scheme == "https"
    assert request.url.host == "api.gitcode.com"
    assert request.url.raw_path.split(b"?", 1)[0] == (
        "/api/v5/repos/team/project/" + suffix
    ).encode("ascii")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/json"
    assert "private-token" not in request.headers
    assert "access_token" not in request.url.params
    assert TOKEN not in str(request.url)
    assert TOKEN.encode() not in request.content
    if operation == "create_branch":
        assert not request.url.params
        assert json.loads(request.content) == kwargs
    else:
        assert request.content == b""
        assert dict(request.url.params) == {
            key: str(value) for key, value in kwargs.items() if value is not None
        }
    assert result == {"echo": "[REDACTED]", "tree": [], "truncated": True}


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        ("timeout", "timeout"),
        ("connection_error", "network_error"),
        ("redirect", "upstream_redirect"),
        ("server_error", "upstream_error"),
        ("invalid_json", "invalid_response"),
        ("oversized", "response_too_large"),
    ],
)
def test_unreleased_primitives_preserve_redacted_limits_and_uncertain_create(
    operation, outcome, code
):
    requests = []

    def handler(request):
        requests.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout(TOKEN, request=request)
        if outcome == "connection_error":
            raise httpx.ConnectError(TOKEN, request=request)
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": f"https://other.example/{TOKEN}"})
        if outcome == "server_error":
            return httpx.Response(503, json={"message": TOKEN})
        if outcome == "invalid_json":
            return httpx.Response(200, content=TOKEN)
        assert outcome == "oversized"
        return httpx.Response(200, content=TOKEN * 10)

    args, kwargs = arguments(operation)
    with GitCodeAPI(TOKEN, max_response_bytes=128, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            getattr(RepoService(api), operation)("team", "project", *args, **kwargs)

    assert len(requests) == 1
    error = raised.value
    assert error.code == code
    assert TOKEN not in str(error)
    assert TOKEN not in json.dumps(error.to_dict())
    if operation == "create_branch":
        assert error.operation_may_have_completed is True
        assert "Verify remote state" in error.message
        assert "do not automatically retry" in error.message
    else:
        assert "operation_may_have_completed" not in error.to_dict()


@pytest.mark.parametrize("status", [401, 403, 409, 422])
def test_definitive_branch_creation_errors_do_not_lookup_or_retry(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"message": TOKEN})

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            RepoService(api).create_branch("team", "project", branch_name="new", refs="main")
    assert len(requests) == 1
    assert raised.value.status_code == status
    assert raised.value.operation_may_have_completed is None
    assert TOKEN not in str(raised.value)


@pytest.mark.parametrize("operation", ["get_tree", "get_commit"])
@pytest.mark.parametrize("ref", ["literal?ref", "literal#ref"])
def test_mcp_transport_retains_its_stricter_decoded_path_policy(operation, ref):
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            getattr(RepoService(api), operation)("team", "project", ref)
    assert raised.value.code == "invalid_path"


@pytest.mark.parametrize("operation", ["list_branches", "get_tree", "list_commits"])
def test_query_credentials_are_still_rejected_by_the_mcp_transport(operation):
    args = (REF,) if operation == "get_tree" else ()
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            getattr(RepoService(api), operation)("team", "project", *args, access_token="synthetic")
    assert raised.value.code == "invalid_arguments"
