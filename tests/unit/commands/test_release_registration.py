from __future__ import annotations

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.compat import CompatStatus, iter_entries
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command


@pytest.mark.parametrize("name", ["list", "ls", "view", "create", "new", "edit", "download", "upload", "delete-asset"])
def test_root_click_entrypoint_registers_direct_release_commands(name):
    result = CliRunner().invoke(main, ["release", name, "--help"])
    assert result.exit_code == 0, result.output
    assert "--repo" in result.output


def test_root_help_and_group_help_list_release_commands():
    runner = CliRunner()
    root = runner.invoke(main, ["--help"])
    assert root.exit_code == 0 and "Manage releases" in root.output
    group = runner.invoke(main, ["release", "--help"])
    assert group.exit_code == 0 and "delete-asset" in group.output


def test_gitcode_proxy_does_not_reinterpret_release_workflows():
    for record in iter_entries(groups=["release"], statuses=[CompatStatus.IMPLEMENTED]):
        assert not record.proxy_allowed
        if record.flag is None:
            with pytest.raises(ProxyError, match="refusing to fall back"):
                validate_gitcode_command(record.command.split() + ["-R", "gitcode.com/owner/repo"])
