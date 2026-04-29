from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import _configure_stdout_encoding, main
from gitcode_cli.errors import APIError


@pytest.fixture
def runner():
    return CliRunner()


class TestCli:
    def test_cli_version(self, runner):
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "gitcode version" in result.output

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
            importlib.reload(cli_mod)
            assert cli_mod.main is not None


class TestConfigureStdoutEncoding:
    def test_reconfigure_called_on_win32_tty(self, monkeypatch):
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.reconfigure = MagicMock()
        mock_stderr.reconfigure = MagicMock()
        mock_stdout.isatty = MagicMock(return_value=True)
        mock_stderr.isatty = MagicMock(return_value=True)
        monkeypatch.setattr("gitcode_cli.cli.sys.stdout", mock_stdout)
        monkeypatch.setattr("gitcode_cli.cli.sys.stderr", mock_stderr)
        monkeypatch.setattr("gitcode_cli.cli.sys.platform", "win32")
        _configure_stdout_encoding()
        mock_stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
        mock_stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

    def test_not_called_on_non_win32(self, monkeypatch):
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.reconfigure = MagicMock()
        mock_stderr.reconfigure = MagicMock()
        monkeypatch.setattr("gitcode_cli.cli.sys.stdout", mock_stdout)
        monkeypatch.setattr("gitcode_cli.cli.sys.stderr", mock_stderr)
        monkeypatch.setattr("gitcode_cli.cli.sys.platform", "darwin")
        _configure_stdout_encoding()
        mock_stdout.reconfigure.assert_not_called()
        mock_stderr.reconfigure.assert_not_called()

    def test_not_called_on_non_tty(self, monkeypatch):
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.reconfigure = MagicMock()
        mock_stderr.reconfigure = MagicMock()
        mock_stdout.isatty = MagicMock(return_value=False)
        mock_stderr.isatty = MagicMock(return_value=False)
        monkeypatch.setattr("gitcode_cli.cli.sys.stdout", mock_stdout)
        monkeypatch.setattr("gitcode_cli.cli.sys.stderr", mock_stderr)
        monkeypatch.setattr("gitcode_cli.cli.sys.platform", "win32")
        _configure_stdout_encoding()
        mock_stdout.reconfigure.assert_not_called()
        mock_stderr.reconfigure.assert_not_called()

    def test_reconfigure_not_called_on_streams_without_reconfigure(self, monkeypatch):
        mock_stdout = MagicMock(spec=["isatty"])
        mock_stderr = MagicMock(spec=["isatty"])
        mock_stdout.isatty = MagicMock(return_value=True)
        mock_stderr.isatty = MagicMock(return_value=True)
        monkeypatch.setattr("gitcode_cli.cli.sys.stdout", mock_stdout)
        monkeypatch.setattr("gitcode_cli.cli.sys.stderr", mock_stderr)
        monkeypatch.setattr("gitcode_cli.cli.sys.platform", "win32")
        _configure_stdout_encoding()

    def test_reconfigure_exception_does_not_crash(self, monkeypatch):
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.reconfigure = MagicMock(side_effect=RuntimeError("not supported"))
        mock_stderr.reconfigure = MagicMock(side_effect=RuntimeError("not supported"))
        mock_stdout.isatty = MagicMock(return_value=True)
        mock_stderr.isatty = MagicMock(return_value=True)
        monkeypatch.setattr("gitcode_cli.cli.sys.stdout", mock_stdout)
        monkeypatch.setattr("gitcode_cli.cli.sys.stderr", mock_stderr)
        monkeypatch.setattr("gitcode_cli.cli.sys.platform", "win32")
        _configure_stdout_encoding()


class TestCompletion:
    def test_completion_zsh(self, runner):
        result = runner.invoke(main, ["completion", "zsh"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_completion_bash(self, runner):
        result = runner.invoke(main, ["completion", "bash"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_completion_invalid_shell(self, runner):
        result = runner.invoke(main, ["completion", "invalid_shell"])
        assert result.exit_code != 0


class TestGlobalErrorHandler:
    def test_api_error_produces_clean_message_without_traceback(self, runner):
        with patch("gitcode_cli.cli.get_token", return_value="fake-token"):
            with patch("gitcode_cli.context.AppContext.client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.get.side_effect = APIError("Not Found", status_code=404)
                mock_client_factory.return_value = mock_client
                result = runner.invoke(main, ["pr", "view", "999999"])
        assert result.exit_code == 1
        assert "error: Not Found" in result.output
        assert "Traceback" not in result.output

    def test_gc_error_produces_clean_message_without_traceback(self, runner):
        from gitcode_cli.errors import AuthError

        with patch("gitcode_cli.cli.get_token", return_value="fake-token"):
            with patch("gitcode_cli.context.AppContext.client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.get.side_effect = AuthError("Invalid token")
                mock_client_factory.return_value = mock_client
                result = runner.invoke(main, ["pr", "list"])
        assert result.exit_code == 1
        assert "error: Invalid token" in result.output
        assert "Traceback" not in result.output
