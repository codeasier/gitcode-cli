"""The issue-only closed selector uses the native lifecycle, not workflow labels or timestamps."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from gitcode_cli.cli import main
from gitcode_cli.commands import issue
from gitcode_cli.context import AppContext
from gitcode_cli.json_projection import project_pr

REPO = "owner/repo"
PATH = f"/repos/{REPO}/issues"
ISSUE = {"number": "2", "state": "closed", "issue_state": "Custom", "finished_at": None}


@pytest.fixture
def api(monkeypatch, tmp_config_dir):
    # No network or real credentials. Only the two existing read methods are available.
    client = Mock(spec=["get"])
    monkeypatch.setattr(AppContext, "client", lambda self: client)
    return client


def invoke(runner, command, *options):
    args = ["--token", "fixture-only", "-R", REPO, "issue", command]
    if command == "view":
        args.append("2")
    return runner.invoke(main, [*args, *options])


def test_list_projects_lifecycle_and_preserves_order(cli_runner, api):
    api.get.return_value = [
        {"number": "5", "state": "opened", "finished_at": "nonempty"},
        ISSUE,
        {"number": "4", "state": "open", "issue_state": "closed"},
        {"number": "3", "state": "custom", "closed": True},
        {"number": "6", "issue_state": "closed", "finished_at": "nonempty"},
        {"number": "8", "state": False},
        {"number": "9", "state": ["closed"]},
    ]
    result = invoke(cli_runner, "list", "--state", "all", "--json", "number, closed")
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert [row["number"] for row in rows] == [5, 2, 4, 3, 6, 8, 9]
    for row, expected in zip(rows, [False, True, False, None, None, None, None]):
        assert row["closed"] is expected
    assert all(list(row) == ["number", "closed"] for row in rows)
    api.get.assert_called_once()
    assert api.get.call_args.args == (PATH,)
    assert api.get.call_args.kwargs["params"]["state"] == "all"


@pytest.mark.parametrize(("state", "expected"), [("opened", False), ("closed", True), ("rejected", None)])
def test_view_uses_just_the_detail(cli_runner, api, state, expected):
    api.get.return_value = {**ISSUE, "state": state}
    result = invoke(cli_runner, "view", "--json", "closed")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert list(data) == ["closed"]
    assert data["closed"] is expected
    api.get.assert_called_once_with(PATH + "/2")


def test_view_combined_with_verified_comments(cli_runner, api, monkeypatch):
    read = Mock(return_value={**ISSUE, "comments": []})
    monkeypatch.setattr(issue, "view_with_comments", read)
    result = invoke(cli_runner, "view", "--json", "closed, comments")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"closed": True, "comments": []}
    read.assert_called_once_with("owner", "repo", "2", "fixture-only")
    api.get.assert_not_called()


def test_discovery_and_empty_collection(cli_runner, api):
    discovery = invoke(cli_runner, "list", "--json")
    assert discovery.exit_code == 1
    assert "closed" in discovery.output.strip().removeprefix("Available fields: ").split(", ")
    api.get.assert_not_called()
    api.get.return_value = []
    result = invoke(cli_runner, "list", "--json", "closed")
    assert result.exit_code == 0
    assert json.loads(result.output) == []
    api.get.assert_called_once()


def test_no_new_field_in_unselected_or_pr_projections(cli_runner, api):
    api.get.return_value = ISSUE
    result = invoke(cli_runner, "view", "--template", "<{{.closed}}>")
    assert result.exit_code == 0
    assert result.output.strip() == "<>"
    assert "closed" not in project_pr(ISSUE)
