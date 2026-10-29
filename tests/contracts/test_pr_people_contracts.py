"""Credential-isolated CLI → real service/client → strict HTTP role contracts."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.pulls import PullRequestService

ORIGIN = "https://people.gitcode.invalid"
TOKEN = "synthetic-people-contract-token"
PREFIX = "/api/v5/repos/owner/repo"
DOCS = Path(__file__).parents[1] / "fixtures/gitcode-api-contracts/pr-people.json"


@pytest.fixture
def http_cli(monkeypatch):
    def reject_credentials(*args, **kwargs):
        raise AssertionError("Contracts must not read ambient credentials")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject_credentials)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=ORIGIN + "/api/v5/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        try:
            yield router, CliRunner(), client
        finally:
            client.close()


def route(router, method, suffix, response, *, payload=None, query=None, status=200, responses=None):
    sequence = iter(responses) if responses is not None else None

    def respond(request):
        assert request.method == method and request.url.path == PREFIX + suffix
        assert request.url.host == "people.gitcode.invalid"
        assert dict(request.url.params) == {"access_token": TOKEN, **(query or {})}
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers and "private-token" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
        return httpx.Response(status, json=next(sequence) if sequence is not None else response)

    return router.request(method, ORIGIN + PREFIX + suffix).mock(side_effect=respond)


def pr(assignees=(), reviewers=(), **overrides):
    return {
        "number": 42,
        "id": 1042,
        "html_url": "https://gitcode.com/owner/repo/pulls/42",
        "assignees": [{"login": x, "id": "id-" + x} for x in assignees],
        "approval_reviewers": [{"login": x, "id": "id-" + x} for x in reviewers],
        **overrides,
    }


def invoke(runner, operation, *flags):
    args = ["--token", TOKEN, "pr", operation, "-R", "owner/repo"]
    if operation == "create":
        args += ["--title", "Title", "--body", "Body", "--base", "main", "--head", "feature"]
    else:
        args += ["42"]
    return runner.invoke(main, [*args, *flags])


@pytest.mark.parametrize(
    "index,method", enumerate(["add_assignees", "remove_assignees", "add_reviewers", "remove_reviewers"])
)
def test_serialized_role_requests_match_official_contract(http_cli, index, method):
    router, _, client = http_cli
    endpoint = json.loads(DOCS.read_text())["endpoints"][index]
    path = endpoint["path"].format(owner="owner", repo="repo", number=42)
    write = route(
        router, endpoint["method"], path.removeprefix(PREFIX), {}, payload=endpoint["json"], query=endpoint["query"]
    )
    getattr(PullRequestService(client), method)("owner", "repo", 42, "alice,bob")
    assert write.call_count == 1


@pytest.mark.parametrize("method", ["add_assignees", "remove_assignees", "add_reviewers", "remove_reviewers"])
@pytest.mark.parametrize("logins", [None, [], 42, "", " ", ",", "alice,", ",bob", "alice, ,bob"])
def test_people_service_rejects_ambiguous_empty_targets_without_http(http_cli, method, logins):
    router, _, client = http_cli
    with pytest.raises(APIError, match="explicit nonempty account logins"):
        getattr(PullRequestService(client), method)("owner", "repo", 42, logins)
    assert not router.calls


def test_create_uses_separate_role_endpoints_and_one_confirmed_readback(http_cli):
    router, runner, _ = http_cli
    route(
        router,
        "POST",
        "/pulls",
        {"number": 42},
        payload={"title": "Title", "body": "Body", "base": "main", "head": "feature", "draft": False},
    )
    read = route(router, "GET", "/pulls/42", None, responses=[pr(("keep",)), pr(("keep", "alice"), ("bob",))])
    route(router, "POST", "/pulls/42/assignees", {"assignees_number": 2}, payload={"assignees": "alice"})
    route(router, "POST", "/pulls/42/reviewers", [], payload={"reviewers": "bob", "add": True})

    result = invoke(runner, "create", "-a", "alice", "-r", "bob", "--json", "number,assignees")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["number"] == 42
    assert [entry.request.method for entry in router.calls] == ["POST", "GET", "POST", "POST", "GET"]
    assert read.call_count == 2


def test_edit_removal_distinguishes_assignee_query_from_reviewer_json(http_cli):
    router, runner, _ = http_cli
    route(router, "GET", "/pulls/42", None, responses=[pr(("alice", "keep"), ("bob",)), pr(("keep",))])
    route(router, "DELETE", "/pulls/42/assignees", {}, query={"assignees": "alice"})
    route(router, "DELETE", "/pulls/42/reviewers", [], payload={"reviewers": "bob"})

    result = invoke(runner, "edit", "--remove-assignee", "alice", "--remove-reviewer", "bob")

    assert result.exit_code == 0, result.output
    assert [entry.request.method for entry in router.calls] == ["GET", "DELETE", "DELETE", "GET"]


@pytest.mark.parametrize("status", [400, 403, 422, 500])
def test_role_failure_after_create_reports_partial_without_repeating_create(http_cli, status):
    router, runner, _ = http_cli
    write = route(
        router,
        "POST",
        "/pulls",
        {"number": 42},
        payload={"title": "Title", "body": "Body", "base": "main", "head": "feature", "draft": False},
    )
    route(router, "GET", "/pulls/42", pr())
    role = route(
        router,
        "POST",
        "/pulls/42/reviewers",
        {"message": "synthetic rejection"},
        payload={"reviewers": "bob", "add": True},
        status=status,
    )

    result = invoke(runner, "create", "-r", "bob")

    assert result.exit_code == 1
    assert "PR #42 may have been created or updated" in result.output and "no write was repeated" in result.output
    assert write.call_count == role.call_count == 1


def test_wrong_pr_number_preflight_never_reaches_writes(http_cli):
    router, runner, _ = http_cli
    route(router, "GET", "/pulls/42", pr(number=43))
    result = invoke(runner, "edit", "-a", "alice")
    assert result.exit_code == 1 and "no PR write was attempted" in result.output
    assert [entry.request.method for entry in router.calls] == ["GET"]
