"""Offline fail-closed flags and unchanged supported mutation contracts."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.adapters.capabilities import CAPABILITY_MESSAGES
from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.compat import CompatStatus, iter_entries

ORIGIN = "https://mutation-guards.gitcode.invalid"
TOKEN = "synthetic-mutation-guard-token"
PREFIX = "/api/v5"


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


def invoke(runner, args):
    return runner.invoke(main, ["--token", TOKEN, "-R", "owner/repo", *args])


def route(router, method, suffix, response, *, payload=None, responses=None):
    sequence = iter(responses) if responses is not None else None

    def respond(request):
        assert request.method == method and request.url.path == PREFIX + suffix
        assert request.url.host == "mutation-guards.gitcode.invalid"
        assert list(request.url.params.multi_items()) == [("access_token", TOKEN)]
        assert request.headers["accept"] == "application/json"
        assert "private-token" not in request.headers and "authorization" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
        return httpx.Response(200, json=next(sequence) if sequence is not None else response)

    return router.request(method, ORIGIN + PREFIX + suffix).mock(side_effect=respond)


@pytest.mark.parametrize("reason", ["completed", "not_planned", "not planned"])
@pytest.mark.parametrize("extra", [[], ["--comment", "Do not post", "--duplicate-of", "12"]])
def test_close_reason_rejects_without_any_http(http_cli, reason, extra):
    router, runner = http_cli
    result = invoke(runner, ["issue", "close", "42", "--reason", reason, *extra])
    assert result.exit_code == 1
    assert CAPABILITY_MESSAGES["ISSUE_CLOSE_REASON"] in result.output
    assert not router.calls


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--title", "Do not update"],
        ["--milestone", "needs a lookup"],
        ["--add-assignee", "@me", "--add-reviewer", "@me"],
        ["--add-label", "new", "--remove-label", "old"],
    ],
)
def test_remove_pr_milestone_rejects_without_any_http(http_cli, extra):
    router, runner = http_cli
    result = invoke(runner, ["pr", "edit", "42", "--remove-milestone", *extra])
    assert result.exit_code == 1
    assert CAPABILITY_MESSAGES["PR_EDIT_REMOVE_MILESTONE"] in result.output
    assert not router.calls


@pytest.mark.parametrize(
    "command,flag,key,help_text",
    [
        ("issue close", "-r/--reason", "ISSUE_CLOSE_REASON", "no verified close-reason API contract"),
        ("pr edit", "--remove-milestone", "PR_EDIT_REMOVE_MILESTONE", "no verified milestone-clearing API contract"),
    ],
)
def test_help_capability_and_registry_are_consistent(http_cli, command, flag, key, help_text):
    router, runner = http_cli
    result = invoke(runner, [*command.split(), "--help"])
    assert result.exit_code == 0
    assert help_text in " ".join(result.output.split())
    assert "Currently unsupported" in result.output
    entry = next(entry for entry in iter_entries() if entry.command == command and entry.flag == flag)
    assert entry.status is CompatStatus.UNSUPPORTED and entry.unsupported_key == key
    assert "currently" in CAPABILITY_MESSAGES[key]
    assert not router.calls


def test_plain_close_preserves_comment_then_supported_state_update(http_cli):
    router, runner = http_cli
    route(router, "GET", "/repos/owner/repo/issues/42", {"number": "42", "title": "Existing", "state": "open"})
    route(router, "POST", "/repos/owner/repo/issues/42/comments", {"id": 1}, payload={"body": "Done"})
    route(
        router,
        "PATCH",
        "/repos/owner/issues/42",
        {"number": "42", "title": "Existing", "state": "closed"},
        payload={"repo": "repo", "title": "Existing", "state": "close"},
    )
    result = invoke(runner, ["issue", "close", "42", "--comment", "Done"])
    assert result.exit_code == 0, result.output
    assert "Closed issue" in result.output
    assert [entry.request.method for entry in router.calls] == ["GET", "POST", "PATCH"]


def test_supported_pr_mixed_edit_retains_people_labels_me_and_milestone(http_cli):
    router, runner = http_cli
    before = {"number": 42, "id": 1042, "assignees": [], "labels": [{"id": 1, "name": "keep"}]}
    after = {
        **before,
        "assignees": [{"id": "user-id", "login": "alice"}],
        "labels": [{"id": 1, "name": "keep"}, {"id": 2, "name": "new"}],
        "milestone": {"number": 7},
    }
    route(router, "GET", "/user", {"login": "alice", "name": "Display Name"})
    read = route(router, "GET", "/repos/owner/repo/pulls/42", None, responses=[before, after])
    route(
        router, "PATCH", "/repos/owner/repo/pulls/42", {"number": 42}, payload={"title": "New", "milestone_number": 7}
    )
    route(router, "POST", "/repos/owner/repo/pulls/42/labels", [], payload=["new"])
    route(router, "POST", "/repos/owner/repo/pulls/42/assignees", {}, payload={"assignees": "alice"})
    result = invoke(
        runner,
        ["pr", "edit", "42", "--title", "New", "--milestone", "7", "--add-assignee", "@me", "--add-label", "new"],
    )
    assert result.exit_code == 0, result.output
    assert read.call_count == 2
    assert [entry.request.method for entry in router.calls] == ["GET", "GET", "PATCH", "POST", "POST", "GET"]
