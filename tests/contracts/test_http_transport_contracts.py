"""Offline service → real CLI client → HTTPX contracts, never provider acceptance."""

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

ORIGIN = "https://contract.gitcode.invalid"
TOKEN = "synthetic-contract-token"
DOCS = Path(__file__).resolve().parents[1] / "fixtures" / "gitcode-api-contracts" / "raw"
ISSUE_CREATE = ("Issues", "post-api-v-5-repos-owner-issues.json")
ISSUE_LIST = ("Issues", "get-api-v-5-repos-owner-repo-issues.json")
PR_COMMENT = ("Pull Requests", "post-api-v-5-repos-owner-repo-pulls-number-comments.json")
PR_REVIEW = ("Pull Requests", "post-api-v-5-repos-owner-repo-pulls-number-review.json")
ISSUE_PAYLOAD = {"repo": "repo", "title": "Contract issue", "body": "Synthetic body"}


@pytest.fixture
def strict_http():
    # An unregistered request must fail, not fall through or become an implicit 200.
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        yield router


@pytest.fixture
def client(strict_http):
    # Construct after the strict router starts. No ambient token/config is read.
    transport = GitCodeClient(token=TOKEN, base_url=f"{ORIGIN}/api/v5/")
    try:
        yield transport
    finally:
        transport.close()


def _contract_route(router, fixture, *, payload=None, query=None, response=None, status=200, error=None):
    contract = json.loads(DOCS.joinpath(*fixture).read_text(encoding="utf-8"))
    path = contract["path"].format(owner="owner", repo="repo", number=42)
    expected_query = {"access_token": TOKEN, **(query or {})}
    assert set(expected_query) <= {field["name"] for field in contract["queryParams"]}
    fields = {field["name"]: field for field in contract["requestBodyFields"]}
    if payload is not None:
        assert set(payload) <= fields.keys()
        assert {name for name, field in fields.items() if field["required"]} <= payload.keys()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == contract["method"]
        assert request.url.scheme == "https" and request.url.host == "contract.gitcode.invalid"
        assert request.url.path == path
        assert sorted(request.url.params.multi_items()) == sorted(
            (name, str(value)) for name, value in expected_query.items()
        ), "HTTP query drift (including duplicate or unexpected authentication parameters)"
        assert request.headers["accept"] == "application/json"
        # These Issue/PR endpoints use CLI query authentication, not repository-only headers or MCP bearer auth.
        assert "private-token" not in request.headers
        assert "authorization" not in request.headers
        if payload is None:
            assert not request.content, "Unexpected HTTP request body"
        else:
            assert request.headers["content-type"] == "application/json"
            actual = json.loads(request.content)
            assert actual == payload, "HTTP JSON body drift"
            types = {"string": str, "integer": int, "boolean": bool}
            for name, value in actual.items():
                assert type(value) is types[fields[name]["type"]], f"HTTP JSON type drift: {name}"
        if error is not None:
            raise error("Synthetic transport failure", request=request)
        return httpx.Response(status, json={} if response is None else response)

    return router.request(contract["method"], ORIGIN + path).mock(side_effect=respond)


def test_issue_create_uses_documented_owner_path_and_repo_body(client, strict_http):
    payload = {**ISSUE_PAYLOAD, "body": "Synthetic body ✓", "labels": "bug,contract"}
    route = _contract_route(strict_http, ISSUE_CREATE, payload=payload, response={"number": "42"}, status=201)

    result = IssueService(client).create(
        "owner", "repo", title="Contract issue", body="Synthetic body ✓", labels="bug,contract", assignee=None
    )

    assert result == {"number": "42"}
    assert route.call_count == 1


@pytest.mark.parametrize(("path", "position"), [(None, None), ("src/space file.py", 7), ("src/main.py", 0)])
def test_pr_comment_uses_path_and_position_not_github_review_fields(client, strict_http, path, position):
    payload = {"body": "Synthetic comment"}
    if path is not None:
        payload.update(path=path, position=position)
    route = _contract_route(strict_http, PR_COMMENT, payload=payload, response={"id": "comment-1"})

    result = PullRequestService(client).comment("owner", "repo", 42, "Synthetic comment", path=path, position=position)

    assert result == {"id": "comment-1"}
    assert route.call_count == 1


@pytest.mark.parametrize(("options", "force"), [({}, False), ({"force": True}, True)])
def test_pr_review_has_documented_force_boolean_and_safe_default(client, strict_http, options, force):
    route = _contract_route(strict_http, PR_REVIEW, payload={"force": force}, response={})

    result = PullRequestService(client).review("owner", "repo", 42, **options)

    assert result == {}
    assert route.call_count == 1


def test_issue_list_preserves_query_values_and_omits_none(client, strict_http):
    route = _contract_route(
        strict_http, ISSUE_LIST, query={"state": "open", "page": 2, "per_page": 10}, response=[]
    )

    result = IssueService(client).list("owner", "repo", state="open", page=2, per_page=10, labels=None)

    assert result == []
    assert route.call_count == 1


@pytest.mark.parametrize("status", [401, 403, 404, 422])
def test_issue_write_http_error_preserves_status_without_retry(client, strict_http, status):
    route = _contract_route(
        strict_http, ISSUE_CREATE, payload=ISSUE_PAYLOAD, status=status, response={"message": "Synthetic API failure"}
    )

    with pytest.raises(APIError, match="Synthetic API failure") as exc:
        IssueService(client).create("owner", "repo", title="Contract issue", body="Synthetic body")

    assert exc.value.status_code == status
    assert route.call_count == 1


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_issue_write_transport_error_is_not_retried(client, strict_http, error):
    route = _contract_route(strict_http, ISSUE_CREATE, payload=ISSUE_PAYLOAD, error=error)

    with pytest.raises(NetworkError, match="Synthetic transport failure"):
        IssueService(client).create("owner", "repo", title="Contract issue", body="Synthetic body")

    assert route.call_count == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/repos/owner/issues"), ("POST", "/repos/owner/repo/issues"), ("POST", "/unregistered")],
)
def test_strict_router_rejects_unregistered_method_or_path(client, strict_http, method, path):
    _contract_route(strict_http, ISSUE_CREATE, payload=ISSUE_PAYLOAD)
    IssueService(client).create("owner", "repo", title="Contract issue", body="Synthetic body")

    with pytest.raises(AssertionError, match="not mocked"):
        client.request(method, path, json=ISSUE_PAYLOAD)


@pytest.mark.parametrize("drift", ["body", "query", "token"])
def test_strict_callback_rejects_body_and_query_drift(client, strict_http, drift):
    _contract_route(strict_http, ISSUE_CREATE, payload=ISSUE_PAYLOAD)
    IssueService(client).create("owner", "repo", title="Contract issue", body="Synthetic body")
    payload = {**ISSUE_PAYLOAD, "event": "REQUEST_CHANGES"} if drift == "body" else ISSUE_PAYLOAD
    params = {"unexpected": "value"} if drift == "query" else {"access_token": "synthetic-other-token"}

    with pytest.raises(AssertionError, match="HTTP JSON body drift" if drift == "body" else "HTTP query drift"):
        client.post("/repos/owner/issues", json=payload, params=None if drift == "body" else params)


def test_strict_callback_distinguishes_boolean_from_equal_integer(client, strict_http):
    _contract_route(strict_http, PR_REVIEW, payload={"force": False})
    PullRequestService(client).review("owner", "repo", 42)

    with pytest.raises(AssertionError, match="HTTP JSON type drift: force"):
        client.post("/repos/owner/repo/pulls/42/review", json={"force": 0})
