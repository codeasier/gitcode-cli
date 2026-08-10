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


class TestAuthStatus:
    def test_status_reports_gh_proxy_target(self, runner, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.auth.get_token", lambda: "u6Gg-secret")
        result = runner.invoke(main, ["auth", "status"], env={"GC_GH_PROXY_ACTIVE": "1"})
        assert result.exit_code == 0
        assert "gitcode.com" in result.output
        assert "✓ Logged in to GitCode" in result.output
        assert "Active account: true" in result.output
        assert "API host: https://api.gitcode.com" in result.output
        assert "Token: u6Gg****" in result.output
        assert "gh proxy: active; commands target GitCode, not GitHub" in result.output

    def test_status_reports_missing_auth_and_proxy_target(self, runner, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.auth.get_token", lambda: (_ for _ in ()).throw(RuntimeError()))
        result = runner.invoke(main, ["auth", "status"], env={"GC_GH_PROXY_ACTIVE": "1"})
        assert result.exit_code == 0
        assert "X Not logged in to GitCode" in result.output
        assert "gh proxy: active; commands target GitCode, not GitHub" in result.output
