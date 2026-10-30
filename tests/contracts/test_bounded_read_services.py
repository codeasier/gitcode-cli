"""Offline wire contracts for existing MCP read shapes exposed by CLI producers.

Comment paths/queries use extracted API fixtures. PR commits and files.json
mirror the existing MCP tools, not a new claim of live provider acceptance.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError, NetworkError
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.pulls import PullRequestService

ORIGIN = "https://bounded-read.gitcode.invalid"
TOKEN = "synthetic-bounded-read-token"
DOCS = Path(__file__).resolve().parents[1] / "fixtures" / "gitcode-api-contracts" / "raw"
READS = ["issue_comments", "pr_comments", "pr_commits", "structured_diff"]


def request_shape(operation):
    if operation == "structured_diff":
        return "/api/v5/repos/owner/repo/pulls/42/files.json", {}
    params = {"page": 3, "per_page": 2}
    if operation == "pr_commits":
        return "/api/v5/repos/owner/repo/pulls/42/commits", params
    if operation == "issue_comments":
        category, resource, number = "Issues", "issues", "I42"
        params.update(order="desc", since="2026-10-01T08:10:30.000+08:00")
    else:
        category, resource, number = "Pull Requests", "pulls", 42
        params.update(direction="desc", comment_type="diff_comment")
    fixture = DOCS / category / f"get-api-v-5-repos-owner-repo-{resource}-number-comments.json"
    contract = json.loads(fixture.read_text(encoding="utf-8"))
    assert contract["method"] == "GET"
    assert set(params) | {"access_token"} <= {field["name"] for field in contract["queryParams"]}
    return contract["path"].format(owner="owner", repo="repo", number=number), params


def read(client, operation, params):
    if operation == "issue_comments":
        return IssueService(client).list_comments_page("owner", "repo", "I42", **params)
    service = PullRequestService(client)
    method = {
        "pr_comments": "list_comments_page",
        "pr_commits": "list_commits_page",
        "structured_diff": "structured_diff",
    }[operation]
    return getattr(service, method)("owner", "repo", 42, **params)


@pytest.fixture
def strict_client():
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=f"{ORIGIN}/api/v5/")
        try:
            yield router, client
        finally:
            client.close()


@pytest.mark.parametrize("operation", READS)
def test_one_get_preserves_query_values_cli_auth_and_raw_json(strict_client, operation):
    router, client = strict_client
    path, params = request_shape(operation)
    result = (
        {"diffs": [{"diff": "@@ -1 +1 @@"}], "diff_refs": {"head_sha": "a" * 40}, "overflow": True}
        if operation == "structured_diff"
        else [{"id": 1}, {"id": 2}]
    )

    def respond(request):
        assert request.method == "GET"
        assert request.url.scheme == "https" and request.url.host == "bounded-read.gitcode.invalid"
        assert request.url.path == path
        assert sorted(request.url.params.multi_items()) == sorted(
            (key, str(value)) for key, value in {**params, "access_token": TOKEN}.items()
        )
        assert request.headers["Accept"] == "application/json"
        assert "private-token" not in request.headers
        assert "Authorization" not in request.headers
        assert request.content == b""
        return httpx.Response(200, json=result)

    route = router.get(ORIGIN + path).mock(side_effect=respond)
    query = {**params, "omitted": None} if params else params

    assert read(client, operation, query) == result
    assert route.call_count == 1


@pytest.mark.parametrize("operation", READS)
def test_no_content_stays_none_instead_of_becoming_an_empty_collection(strict_client, operation):
    router, client = strict_client
    path, params = request_shape(operation)
    route = router.get(ORIGIN + path).respond(204)

    assert read(client, operation, params) is None
    assert route.call_count == 1


@pytest.mark.parametrize("operation", READS)
@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_cli_errors_stay_redacted_without_a_followup_request(strict_client, operation, status):
    router, client = strict_client
    path, params = request_shape(operation)
    route = router.get(ORIGIN + path).respond(status, json={"message": TOKEN})

    with pytest.raises(APIError) as raised:
        read(client, operation, params)

    assert raised.value.status_code == status
    assert TOKEN not in str(raised.value)
    assert "[REDACTED]" in str(raised.value)
    assert route.call_count == 1


@pytest.mark.parametrize("operation", READS)
def test_cli_timeout_stays_redacted_without_a_followup_request(strict_client, operation):
    router, client = strict_client
    path, params = request_shape(operation)

    def timeout(request):
        raise httpx.ReadTimeout(TOKEN, request=request)

    route = router.get(ORIGIN + path).mock(side_effect=timeout)
    with pytest.raises(NetworkError, match="Request timed out") as raised:
        read(client, operation, params)

    assert TOKEN not in str(raised.value)
    assert route.call_count == 1
