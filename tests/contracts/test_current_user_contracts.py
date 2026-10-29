"""Offline CLI → service → HTTP contracts for explicit @me aliases."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://current-user.gitcode.invalid"
TOKEN = "synthetic-current-user-contract-token"
PREFIX = "/api/v5"
ISSUE = {
    "number": "42",
    "title": "Existing",
    "html_url": "https://gitcode.com/owner/repo/issues/42",
    "assignees": [{"login": "alice"}, {"login": "keep"}],
}


@pytest.fixture
def http_cli(monkeypatch):
    def reject_credentials(*args, **kwargs):
        raise AssertionError("Contracts must not read ambient credentials")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject_credentials)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=ORIGIN + PREFIX + "/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        try:
            yield router, CliRunner()
        finally:
            client.close()


def route(router, method, suffix, response, *, payload=None, query=None, status=200):
    def respond(request):
        assert request.method == method and request.url.path == PREFIX + suffix
        assert request.url.host == "current-user.gitcode.invalid"
        expected = {"access_token": TOKEN, **(query or {})}
        assert sorted(request.url.params.multi_items()) == sorted((key, str(value)) for key, value in expected.items())
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers and "private-token" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
        return httpx.Response(status, json=response)

    return router.request(method, ORIGIN + PREFIX + suffix).mock(side_effect=respond)


def invoke(runner, args):
    return runner.invoke(main, ["--token", TOKEN, "-R", "owner/repo", *args])


@pytest.mark.parametrize("group,author_key", [("pr", "author"), ("issue", "creator")])
def test_list_resolves_author_and_assignee_in_one_lookup(http_cli, group, author_key):
    router, runner = http_cli
    current = route(router, "GET", "/user", {"login": "alice", "name": "Wrong Display Name"})
    suffix = "/repos/owner/repo/" + ("pulls" if group == "pr" else "issues")
    route(router, "GET", suffix, [], query={author_key: "alice", "assignee": "alice", "page": 1, "per_page": 30})

    result = invoke(runner, [group, "list", "-A", "@me", "-a", "@me", "--json", "number"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == []
    assert current.call_count == 1
    assert [entry.request.url.path for entry in router.calls] == [PREFIX + "/user", PREFIX + suffix]


def test_issue_create_serializes_resolved_login_not_literal_or_display_name(http_cli):
    router, runner = http_cli
    route(router, "GET", "/user", {"login": "alice", "name": "Wrong Display Name"})
    create = route(
        router,
        "POST",
        "/repos/owner/issues",
        ISSUE,
        payload={"repo": "repo", "title": "Title", "body": "Body", "assignee": "alice"},
    )

    result = invoke(runner, ["issue", "create", "-t", "Title", "-b", "Body", "-a", "@me"])

    assert result.exit_code == 0, result.output
    assert ISSUE["html_url"] in result.output
    assert create.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "POST"]


@pytest.mark.parametrize("flag,expected", [("--add-assignee", "alice"), ("--remove-assignee", "keep")])
def test_issue_edit_resolves_before_read_and_update(http_cli, flag, expected):
    router, runner = http_cli
    route(router, "GET", "/user", {"login": "alice", "name": "Wrong Display Name"})
    route(router, "GET", "/repos/owner/repo/issues/42", ISSUE)
    update = route(
        router,
        "PATCH",
        "/repos/owner/issues/42",
        ISSUE,
        payload={"repo": "repo", "title": "Existing", "assignee": expected},
    )

    result = invoke(runner, ["issue", "edit", "42", flag, "@me"])

    assert result.exit_code == 0, result.output
    assert update.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "GET", "PATCH"]


ALIAS_COMMANDS = [
    ["pr", "list", "-A", "@me"],
    ["pr", "list", "-a", "@me"],
    ["issue", "list", "-A", "@me"],
    ["issue", "list", "-a", "@me"],
    ["issue", "create", "-t", "Title", "-b", "Body", "-a", "@me"],
    ["issue", "edit", "42", "--add-assignee", "@me"],
    ["issue", "edit", "42", "--remove-assignee", "@me"],
]


@pytest.mark.parametrize("args", ALIAS_COMMANDS)
@pytest.mark.parametrize("current", [{}, {"name": "display-name"}, {"login": ""}, {"login": "bad login"}, None])
def test_unverifiable_alias_never_reaches_domain_request(http_cli, args, current):
    router, runner = http_cli
    route(router, "GET", "/user", current)

    result = invoke(runner, args)

    assert result.exit_code == 1
    assert "failed to resolve @me" in result.output and "no write was attempted" in result.output
    assert [entry.request.url.path for entry in router.calls] == [PREFIX + "/user"]


@pytest.mark.parametrize("args", ALIAS_COMMANDS)
@pytest.mark.parametrize("status", [401, 403, 500])
def test_lookup_failure_is_not_retried_and_never_reaches_domain_request(http_cli, args, status):
    router, runner = http_cli
    route(router, "GET", "/user", {"message": "synthetic rejection"}, status=status)

    result = invoke(runner, args)

    assert result.exit_code == 1
    assert "lookup failed; no write was attempted" in result.output
    assert len(router.calls) == 1


@pytest.mark.parametrize("group,author_key", [("pr", "author"), ("issue", "creator")])
def test_plain_list_filters_skip_identity_lookup(http_cli, group, author_key):
    router, runner = http_cli
    suffix = "/repos/owner/repo/" + ("pulls" if group == "pr" else "issues")
    route(router, "GET", suffix, [], query={author_key: "alice", "assignee": "bob", "page": 1, "per_page": 30})

    result = invoke(runner, [group, "list", "-A", "alice", "-a", "bob", "--json", "number"])

    assert result.exit_code == 0, result.output
    assert len(router.calls) == 1


def test_plain_issue_create_skips_identity_lookup(http_cli):
    router, runner = http_cli
    route(
        router,
        "POST",
        "/repos/owner/issues",
        ISSUE,
        payload={"repo": "repo", "title": "Title", "body": "Body", "assignee": "bob"},
    )
    result = invoke(runner, ["issue", "create", "-t", "Title", "-b", "Body", "-a", "bob"])
    assert result.exit_code == 0, result.output
    assert len(router.calls) == 1


def test_zero_limit_pr_list_skips_all_requests(http_cli):
    router, runner = http_cli
    result = invoke(runner, ["pr", "list", "-A", "@me", "-L", "0", "--json", "number"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == []
    assert not router.calls
