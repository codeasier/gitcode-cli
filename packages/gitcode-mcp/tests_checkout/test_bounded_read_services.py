"""Unreleased Issue/PR producers, selected only with the installed CLI checkout.

Published pygitcode 0.1.7 does not provide these primitives. Keep this module
outside tests/ and tests_source/, which also validate published artifacts.
Production MCP tools do not consume the new methods yet; result policy remains
with the consumer rather than the raw single-request service methods.
"""

import json

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError

TOKEN = "synthetic-bounded-service-token"
PAGED_READS = ["issue_comments", "pr_comments", "pr_commits"]
READS = [*PAGED_READS, "structured_diff"]


def read(api, operation):
    params = {"page": 3, "per_page": 2}
    if operation == "issue_comments":
        return api.issues.list_comments_page("team", "project", "42", **params)
    if operation == "pr_comments":
        return api.pulls.list_comments_page("team", "project", 42, **params)
    if operation == "pr_commits":
        return api.pulls.list_commits_page("team", "project", 42, **params)
    assert operation == "structured_diff"
    return api.pulls.structured_diff("team", "project", 42)


@pytest.mark.parametrize("operation", READS)
def test_primitives_keep_one_bounded_bearer_only_json_request(operation, monkeypatch):
    requests = []
    options = []
    original_client = httpx.Client

    def client(**kwargs):
        options.append(kwargs)
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    payload = (
        {"diffs": [{"diff": TOKEN}], "diff_refs": {"head_sha": "a" * 40}, "overflow": True}
        if operation == "structured_diff"
        else [{"id": 1, "body": TOKEN}, {"id": 2}]
    )

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    with GitCodeAPI(TOKEN, timeout=7.5, transport=httpx.MockTransport(handler)) as api:
        result = read(api, operation)

    assert len(requests) == len(options) == 1
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert options[0]["timeout"] == 7.5
    request = requests[0]
    suffix = {
        "issue_comments": "issues/42/comments",
        "pr_comments": "pulls/42/comments",
        "pr_commits": "pulls/42/commits",
        "structured_diff": "pulls/42/files.json",
    }[operation]
    assert request.method == "GET"
    assert request.url.scheme == "https" and request.url.host == "api.gitcode.com"
    assert request.url.path == "/api/v5/repos/team/project/" + suffix
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/json"
    assert "private-token" not in request.headers
    assert "access_token" not in request.url.params
    assert TOKEN not in str(request.url)
    assert request.content == b""
    assert dict(request.url.params) == (
        {} if operation == "structured_diff" else {"page": "3", "per_page": "2"}
    )
    assert result == json.loads(json.dumps(payload).replace(TOKEN, "[REDACTED]"))


@pytest.mark.parametrize("operation", PAGED_READS)
@pytest.mark.parametrize("items", [[], [{"id": 1}], [{"id": 1}, {"id": 2}]])
def test_consumer_page_policy_still_owns_next_page_without_eager_fetching(operation, items):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=items)

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        result = api.page_result(read(api, operation), page=3, per_page=2)

    assert result == {
        "data": items,
        "page": 3,
        "per_page": 2,
        "next_page": 4 if len(items) == 2 else None,
        "pagination_mode": "upstream",
        "pagination_note": "A full page may have a next page; that next page can be empty.",
    }
    assert len(requests) == 1


@pytest.mark.parametrize("operation", PAGED_READS)
@pytest.mark.parametrize("items", [None, {}, [{"id": 1}, {"id": 2}, {"id": 3}]])
def test_malformed_or_overfull_pages_remain_the_consumers_validation_responsibility(
    operation, items
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=items)

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        raw = read(api, operation)
        assert raw == items
        with pytest.raises(GitCodeError) as raised:
            api.page_result(raw, page=3, per_page=2)

    assert raised.value.code == "invalid_response"
    assert len(requests) == 1


@pytest.mark.parametrize("operation", READS)
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
def test_read_failures_keep_mcp_limits_redaction_and_no_retry(operation, outcome, code):
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
        if outcome == "invalid_unicode":
            return httpx.Response(200, content=b"\xff" + TOKEN.encode())
        assert outcome == "oversized"
        return httpx.Response(200, content=TOKEN * 10)

    with GitCodeAPI(TOKEN, max_response_bytes=128, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            read(api, operation)

    assert len(requests) == 1
    error = raised.value
    assert error.code == code
    assert TOKEN not in str(error)
    assert TOKEN not in json.dumps(error.to_dict())
    assert "operation_may_have_completed" not in error.to_dict()


@pytest.mark.parametrize("operation", READS)
@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_status_errors_keep_their_safe_codes_and_rate_limit_metadata(operation, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"message": TOKEN}, headers={"Retry-After": "17"})

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            read(api, operation)

    assert len(requests) == 1
    assert raised.value.code == {
        401: "authentication_failed",
        403: "permission_denied",
        404: "not_found",
        429: "rate_limited",
    }[status]
    assert raised.value.status_code == status
    assert raised.value.retry_after == (17 if status == 429 else None)
    assert TOKEN not in json.dumps(raised.value.to_dict())


def test_existing_files_collection_and_text_diff_are_distinct_from_structured_diff():
    requests = []
    files = [{"filename": f"file_{index}.py"} for index in range(101)]
    structured = {"diffs": [], "diff_refs": {"head_sha": "a" * 40}}

    def handler(request):
        requests.append(request)
        assert not request.url.params
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=files)
        if request.url.path.endswith("/files.json"):
            return httpx.Response(200, json=structured)
        assert request.url.path.endswith("/diff")
        assert request.headers["Accept"] == "text/plain"
        return httpx.Response(200, text="diff --git a/file b/file")

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        assert api.pulls.list_files("team", "project", 42) == files
        assert api.pulls.structured_diff("team", "project", 42) == structured
        assert api.pulls.diff("team", "project", 42) == "diff --git a/file b/file"

    assert len(requests) == 3
