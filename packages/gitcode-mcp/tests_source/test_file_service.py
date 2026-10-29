"""Explicit shared-service contracts, separate from ordinary tests/ selection.

CI selects this directory for verified published CLI artifacts and checkout
compatibility. Both install the CLI separately and check its hashes before
running these contracts; no sibling-source import is used.
"""

import json
from urllib.parse import quote

import httpx
import pytest
from gitcode_cli.services import FileService, RepoService

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

TOKEN = "synthetic-file-service-token"
SHA = "A" * 40
PATH = "source files/中文.py"
CONTENT = "cHJpdmF0ZSBmaWxlIGNvbnRlbnQ="


def arguments(operation):
    if operation == "get":
        return {"ref": "feature/中文 space", "omitted": None}
    payload = {"branch": "feature/files", "message": "Publish file"}
    if operation != "delete":
        payload["content"] = CONTENT
    if operation != "create":
        payload["sha"] = SHA
    return payload


@pytest.mark.parametrize(
    ("operation", "method"),
    [("get", "GET"), ("create", "POST"), ("update", "PUT"), ("delete", "DELETE")],
)
def test_service_uses_real_mcp_transport_once_with_unchanged_payload(
    operation, method, monkeypatch
):
    requests = []
    options = []
    client_type = httpx.Client

    def client(**kwargs):
        options.append(kwargs)
        return client_type(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"content": {"sha": SHA}, "echo": TOKEN})

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        result = getattr(FileService(api), operation)(
            "team", "project", PATH, **arguments(operation)
        )

    assert len(requests) == 1
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    request = requests[0]
    assert request.method == method
    assert request.url.scheme == "https"
    assert request.url.host == "api.gitcode.com"
    assert request.url.raw_path.split(b"?", 1)[0] == (
        "/api/v5/repos/team/project/contents/" + quote(PATH, safe="/")
    ).encode("ascii")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "private-token" not in request.headers
    assert "access_token" not in request.url.params
    assert TOKEN not in str(request.url)
    assert TOKEN.encode() not in request.content
    if operation == "get":
        assert dict(request.url.params) == {"ref": "feature/中文 space"}
        assert request.content == b""
    else:
        assert not request.url.params
        assert json.loads(request.content) == arguments(operation)
    assert result == {"content": {"sha": SHA}, "echo": "[REDACTED]"}


def test_repo_contents_delegation_uses_the_same_mcp_transport_and_encodes_query_once():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"path": PATH})

    ref = "feature/中文+?%2F#"
    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        assert RepoService(api).contents("team", "project", PATH, ref=ref) == {"path": PATH}
    assert len(requests) == 1
    assert requests[0].url.params["ref"] == ref
    assert requests[0].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("operation", ["get", "create", "update", "delete"])
@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        ("timeout", "timeout"),
        ("connection_error", "network_error"),
        ("redirect", "upstream_redirect"),
        ("server_error", "upstream_error"),
        ("invalid_json", "invalid_response"),
        ("invalid_unicode", "invalid_response"),
        ("oversized", "response_too_large"),
    ],
)
def test_transport_failures_keep_bounded_redacted_uncertain_semantics(operation, outcome, code):
    requests = []
    reflected = f"{TOKEN} {CONTENT}"

    def handler(request):
        requests.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout(reflected, request=request)
        if outcome == "connection_error":
            raise httpx.ConnectError(reflected, request=request)
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": f"https://other.example/{TOKEN}"})
        if outcome == "server_error":
            return httpx.Response(503, json={"message": reflected})
        if outcome == "invalid_json":
            return httpx.Response(200, content=reflected)
        if outcome == "invalid_unicode":
            return httpx.Response(200, content=b"\xff" + reflected.encode())
        assert outcome == "oversized"
        return httpx.Response(200, content=(reflected * 10).encode())

    with GitCodeAPI(TOKEN, max_response_bytes=128, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            getattr(FileService(api), operation)("team", "project", PATH, **arguments(operation))

    assert len(requests) == 1
    error = raised.value
    assert error.code == code
    assert TOKEN not in str(error)
    assert CONTENT not in str(error)
    assert TOKEN not in json.dumps(error.to_dict())
    assert CONTENT not in json.dumps(error.to_dict())
    if operation == "get":
        assert "operation_may_have_completed" not in error.to_dict()
    else:
        assert error.operation_may_have_completed is True
        assert "Verify remote state" in error.message
        assert "do not automatically retry" in error.message


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("status", [401, 403, 409, 422])
def test_definitive_write_errors_do_not_refresh_sha_or_retry(operation, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"message": TOKEN})

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            getattr(FileService(api), operation)("team", "project", PATH, **arguments(operation))
    assert len(requests) == 1
    assert raised.value.status_code == status
    assert raised.value.operation_may_have_completed is None
    assert TOKEN not in str(raised.value)


@pytest.mark.parametrize("path", ["README?.md", "README#.md"])
def test_mcp_transport_retains_its_own_stricter_decoded_path_policy(path):
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            FileService(api).get("team", "project", path)
    assert raised.value.code == "invalid_path"


@pytest.mark.parametrize("path", ["README?.md", "README#.md", "100%.md", "literal%2F.md"])
def test_production_tool_entry_point_keeps_its_independent_filename_policy(path):
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        tools = GitCodeTools(api)
        with pytest.raises(GitCodeError) as raised:
            tools.call(
                "gitcode_get_file_contents", {"owner": "team", "repo": "project", "path": path}
            )
    assert raised.value.code == "invalid_arguments"


def test_mcp_query_credentials_remain_rejected_before_transport():
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            FileService(api).get("team", "project", PATH, access_token="not-a-real-token")
    assert raised.value.code == "invalid_arguments"
