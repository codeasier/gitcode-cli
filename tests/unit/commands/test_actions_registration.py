"""Check direct invocation and retain fail-closed GitCode gh proxy routing."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.actions_client import ActionsClient
from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

COMMANDS = [
    ("run", "list"),
    ("run", "view"),
    ("run", "watch"),
    ("run", "rerun"),
    ("run", "cancel"),
    ("workflow", "list"),
    ("workflow", "view"),
    ("workflow", "run"),
    ("pr", "checks"),
]


@pytest.mark.parametrize("argv", COMMANDS)
def test_production_route_shows_help_but_gh_proxy_refuses(argv, tmp_config_dir, monkeypatch):
    monkeypatch.delenv("GC_TOKEN", raising=False)
    gc = CliRunner().invoke(main, [*argv, "--help"])
    assert gc.exit_code == 0, gc.output
    assert "USAGE" in gc.output
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(argv)


@pytest.mark.parametrize(
    "argv, path, query",
    [
        (
            ["-R", "o/r", "run", "list", "--pr", "21"],
            "/api/v8/repos/o/r/actions/runs",
            {"page": "1", "per_page": "20", "pull_request_id": "21"},
        ),
        (["workflow", "list", "-R", "o/r"], "/api/v8/repos/o/r/actions/workflows", {"page": "1", "per_page": "20"}),
    ],
)
def test_real_cli_root_routes_with_repo_and_synthetic_token(monkeypatch, tmp_config_dir, argv, path, query):
    synthetic_token = "test-cli-v8"
    monkeypatch.setenv("GC_TOKEN", synthetic_token)
    requests = []

    def handle(request: httpx.Request):
        requests.append(request.url.path)
        assert (request.method, request.url.host, request.url.path) == ("GET", "api.gitcode.com", path)
        assert dict(request.url.params) == {**query, "access_token": synthetic_token}
        key = "workflow_runs" if path.endswith("/runs") else "workflows"
        return httpx.Response(200, json={key: [], "total_count": 0})

    def fake_actions_client(token):
        return ActionsClient(token, transport=httpx.MockTransport(handle))

    monkeypatch.setattr("gitcode_cli.commands.actions.ActionsClient", fake_actions_client)
    got = CliRunner().invoke(main, argv)
    assert got.exit_code == 0, got.output
    assert json.loads(got.output)["total_count"] == 0
    assert requests == [path]
