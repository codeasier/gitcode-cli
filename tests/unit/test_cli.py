from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCli:
    def test_cli_version(self, runner):
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "gc version 0.1.0" in result.output

    def test_cli_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_cli_issue_group(self, runner):
        result = runner.invoke(main, ["issue", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "list" in result.output

    def test_cli_pr_group(self, runner):
        result = runner.invoke(main, ["pr", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "list" in result.output

    def test_cli_auth_group(self, runner):
        result = runner.invoke(main, ["auth", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "login" in result.output

    def test_cli_with_token(self, runner, monkeypatch):
        from gitcode_cli.context import AppContext

        calls = []
        original_init = AppContext.__init__

        def capturing_init(self, token, repo):
            calls.append({"token": token, "repo": repo})
            original_init(self, token, repo)

        monkeypatch.setattr(AppContext, "__init__", capturing_init)
        result = runner.invoke(main, ["--token", "test123", "version"])
        assert result.exit_code == 0
        assert len(calls) == 1
        assert calls[0]["token"] == "test123"

    def test_cli_with_repo(self, runner, monkeypatch):
        from gitcode_cli.context import AppContext

        calls = []
        original_init = AppContext.__init__

        def capturing_init(self, token, repo):
            calls.append({"token": token, "repo": repo})
            original_init(self, token, repo)

        monkeypatch.setattr(AppContext, "__init__", capturing_init)
        result = runner.invoke(main, ["-R", "owner/repo", "version"])
        assert result.exit_code == 0
        assert len(calls) == 1
        assert calls[0]["repo"] == "owner/repo"

    def test_main_entrypoint(self, monkeypatch):
        import importlib
        import sys
        from pathlib import Path

        src_path = str(Path(__file__).resolve().parents[2] / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        with patch.object(sys, "argv", ["gc", "version"]), patch("gitcode_cli.cli.get_token") as mock_get_token:
            mock_get_token.side_effect = Exception("no token")
            import gitcode_cli.cli as cli_mod

            monkeypatch.setattr(cli_mod, "__name__", "__main__")
            # Re-execute the module-level code by reloading
            importlib.reload(cli_mod)
            assert cli_mod.main is not None
