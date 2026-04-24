from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestAuthLogin:
    def test_auth_login_prompt(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login"], input="mytoken\n")
        assert result.exit_code == 0
        assert "Authentication saved." in result.output
        config_path = tmp_config_dir / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["token"] == "mytoken"

    def test_auth_login_with_token_reads_from_stdin_without_prompting(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login", "--with-token"], input="mytoken\n")
        assert result.exit_code == 0
        assert "GitCode token" not in result.output
        assert "Authentication saved." in result.output
        config_path = tmp_config_dir / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["token"] == "mytoken"

    def test_auth_login_with_token_rejects_blank_stdin(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login", "--with-token"], input="\n")
        assert result.exit_code != 0
        assert "No token provided on stdin." in result.output
        config_path = tmp_config_dir / "config.json"
        assert not config_path.exists()
