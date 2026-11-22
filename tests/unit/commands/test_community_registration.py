"""Prove the actual entrypoint, compat registry and proxy agree on direct-only commands."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.compat import CompatStatus, iter_entries
from gitcode_cli.context import AppContext
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

DIRECT = {
    "search": ["repos", "issues", "prs", "users"],
    "label": ["list", "create", "edit", "delete", "clone"],
    "org": ["list"],
    "discussion": ["list", "view", "create", "edit", "comment"],
}
SUBCOMMANDS = [f"{group} {cmd}" for group, commands in DIRECT.items() for cmd in commands]


def test_groups_are_visible_in_main_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    for group in DIRECT:
        assert f"{group}:" in result.output


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_command_is_in_real_entrypoint_but_not_proxy(name):
    command = name.split()
    result = CliRunner().invoke(main, [*command, "--help"])
    assert result.exit_code == 0, result.output
    assert "USAGE" in result.output or "Usage" in result.output
    [entry] = [e for e in iter_entries(groups=[command[0]]) if e.command == name and e.flag is None]
    assert entry.status is CompatStatus.IMPLEMENTED and not entry.proxy_allowed
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(command)


@pytest.mark.parametrize(
    ("argv", "path", "params"),
    [
        (["org", "ls"], "/users/orgs", {"page": 1, "per_page": 30}),
        (
            ["-R", "example/project", "discussion", "ls"],
            "/repos/example/project/discuss",
            {"page": 1, "per_page": 100, "sort": "created", "direction": "desc"},
        ),
    ],
)
def test_community_aliases_execute_through_main_without_network(monkeypatch, tmp_config_dir, argv, path, params):
    client = MagicMock()
    client.get.return_value = []
    monkeypatch.setattr(AppContext, "client", lambda _: client)
    result = CliRunner().invoke(main, argv)
    assert result.exit_code == 0, result.output
    client.get.assert_called_once_with(path, params=params)
