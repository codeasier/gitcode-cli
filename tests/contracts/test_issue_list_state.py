"""Repository issue-list state is narrowed by the CLI, not the SDK or formatter."""

import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient


@pytest.mark.parametrize(
    ("args", "state", "numbers"),
    [
        ([], "open", [1]),
        (["--state", "open"], "open", [1]),
        (["--state", "closed"], "closed", [2]),
        (["--state", "all"], "all", [1, 2]),
    ],
)
@pytest.mark.parametrize("filtered", [False, True], ids=["bare", "author-and-search"])
def test_list_selects_state_on_the_provider(monkeypatch, args, state, numbers, filtered):
    states = []
    rows = [{"number": "1", "state": "open"}, {"number": "2", "state": "closed"}]

    def respond(request):
        assert request.method == "GET" and request.url.path == "/api/v5/repos/o/r/issues"
        params = request.url.params
        assert params.get("search") == ("keyword" if filtered else None)
        assert params.get("creator") == ("alice" if filtered else None)
        states.append(params.get("state"))
        # GitCode defaults to all states when the caller omits the parameter.
        selected = params.get("state", "all")
        return httpx.Response(200, json=[row for row in rows if selected == "all" or row["state"] == selected])

    token = "synthetic-issue-list-state"
    client = GitCodeClient(token, "https://issue-list.invalid/api/v5/", transport=httpx.MockTransport(respond))
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    try:
        filters = ["-S", "keyword", "-A", "alice"] if filtered else []
        result = CliRunner().invoke(
            main, ["--token", token, "-R", "o/r", "issue", "list", *args, *filters, "--json", "number"]
        )
    finally:
        client.close()
    assert result.exit_code == 0, result.output
    assert [row["number"] for row in json.loads(result.output)] == numbers
    assert states == [state]
