"""Workflow definitions are not runs. Check the exact wire access and the machine-readable CLI result."""

from __future__ import annotations

import json
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.actions_client import ActionsClient
from gitcode_cli.cli import main
from gitcode_cli.compat.registry import render_markdown_report
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

TOKEN = "workflow-fixture-token"
FIRST = {"workflow_id": "0009", "name": "构建 🚀", "file_path": ".gitcode/workflows/build.yml", "state": "ACTIVE"}


@pytest.fixture
def endpoint(monkeypatch, tmp_config_dir):
    calls = []
    replies = []
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))

    def handle(request):
        calls.append((request.method, request.url.path))
        assert request.url.host == "api.gitcode.com"
        assert request.url.path == "/api/v8/repos/o/r/actions/workflows" and request.method == "GET"
        assert not request.content and "private-token" not in request.headers
        reply, query = replies.pop(0)
        assert dict(request.url.params) == {"access_token": TOKEN, **query}
        return httpx.Response(200, json=reply)

    monkeypatch.setattr(
        "gitcode_cli.commands.actions.ActionsClient",
        lambda token: ActionsClient(token, transport=httpx.MockTransport(handle)),
    )

    def expect(rows, total=None, *, page=1, limit=20):
        replies.append(
            (
                {"total_count": len(rows) if total is None else total, "workflows": rows},
                {"page": str(page), "per_page": str(limit)},
            )
        )

    def invoke(*args):
        return runner.invoke(main, ["--token", TOKEN, "-R", "gitcode.com/o/r", "workflow", "list", *args])

    yield expect, invoke, calls
    assert not replies


def test_explicit_page_projects_native_definition_fields_only(endpoint):
    expect, invoke, calls = endpoint
    second = {**FIRST, "workflow_id": "wf-b", "state": "new-native-state", "name": "Build B"}
    rows = [{**FIRST, "workflow_run_id": "wrong", "yaml": "private", "inputs": {"secret": TOKEN}}, second]
    expect(rows, total=5, page=2, limit=2)
    result = invoke("-R", "o/r", "--page", "2", "-L2", "--json", "state, id,name,path")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [
        {"state": row["state"], "id": row["workflow_id"], "name": row["name"], "path": row["file_path"]} for row in rows
    ]
    assert list(json.loads(result.stdout)[0]) == ["state", "id", "name", "path"]
    assert result.stderr == "" and TOKEN not in result.stdout
    assert len(calls) == 1  # More rows exist: no next page and no lookup of runs, files or YAML.


def test_subset_does_not_read_unselected_values_or_guess_active(endpoint):
    expect, invoke, _ = endpoint
    expect([{**FIRST, "state": "disabled_manually", "workflow_id": TOKEN}])
    result = invoke("--json", "state")
    assert result.exit_code == 0 and json.loads(result.stdout) == [{"state": "disabled_manually"}]


def test_empty_page_and_default_envelope(endpoint):
    expect, invoke, _ = endpoint
    expect([], total=1, page=2)
    result = invoke("--page", "2", "--json", "id")
    assert result.exit_code == 0 and json.loads(result.stdout) == []
    expect([FIRST], total=2, limit=1)
    result = invoke("-L1")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"workflows": [FIRST], "total_count": 2, "page": 1, "next_page": 2}


@pytest.mark.parametrize(
    "args",
    [
        ("--json",),
        ("--json", ""),
        ("--json", "name,"),
        ("--json", "name, name"),
        ("--json", "id", "--json", "name"),
        ("--json", "run_id"),
        ("-R", "other/repo", "--json", "id"),
    ],
)
def test_bad_projection_makes_no_requests(endpoint, args):
    _, invoke, calls = endpoint
    result = invoke(*args)
    assert result.exit_code == 2 and result.stdout == "" and not calls


@pytest.mark.parametrize(
    "native,field,value",
    [
        ("workflow_id", "id", 9),
        ("file_path", "path", None),
        ("name", "name", {}),
        ("state", "state", False),
        ("workflow_id", "id", ""),
        ("name", "name", TOKEN),
        ("file_path", "path", "x?access_token=fixture"),
        ("state", "state", TOKEN),
    ],
)
def test_unusable_selected_value_on_last_row_fails_without_partial_output(endpoint, native, field, value):
    expect, invoke, calls = endpoint
    expect([FIRST, {**FIRST, native: value}])
    result = invoke("--json", field)
    assert result.exit_code == 1 and result.stdout == "" and result.stderr
    assert TOKEN not in result.stderr and "access_token=fixture" not in result.stderr and len(calls) == 1


def test_incomplete_page_is_not_a_successful_empty_projection(endpoint):
    expect, invoke, _ = endpoint
    expect([], total=1)
    result = invoke("--json", "id")
    assert result.exit_code == 1 and result.stdout == ""


def test_documented_selection_does_not_enable_proxy(endpoint):
    _, invoke, calls = endpoint
    result = invoke("--help")
    assert result.exit_code == 0 and "JSON FIELDS" in result.stdout and "id, name, path, state" in result.stdout
    assert "| `workflow list` | `--json` | implemented | Direct gc only:" in render_markdown_report()
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(("workflow", "list", "--json", "id"))
    assert not calls
