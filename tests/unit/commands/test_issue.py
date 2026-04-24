"""Tests for gitcode_cli.commands.issue."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.get = MagicMock(return_value=[])
    client.post = MagicMock(
        return_value={"number": "42", "html_url": "https://example.com/42", "title": "Test", "id": 99}
    )
    client.patch = MagicMock(return_value={"number": "42", "html_url": "https://example.com/42", "title": "Test"})
    client.delete = MagicMock(return_value=None)

    from gitcode_cli import context

    monkeypatch.setattr(context.AppContext, "client", lambda self: client)
    return client


@pytest.fixture
def mock_repo(monkeypatch):
    from gitcode_cli import repo

    monkeypatch.setattr(repo, "resolve_repo", lambda x=None: ("owner", "repo"))
    # Also patch in commands.issue since it binds locally
    import gitcode_cli.commands.issue as issue_mod

    monkeypatch.setattr(issue_mod, "resolve_repo", lambda x=None: ("owner", "repo"))


class TestIssueList:
    def test_default(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": "1", "state": "open", "title": "First"},
            {"number": "2", "state": "closed", "title": "Second"},
        ]
        result = runner.invoke(main, ["issue", "list"])
        assert result.exit_code == 0
        assert "#1" in result.output
        mock_client.get.assert_called_once()

    def test_with_options(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            ["issue", "list", "-s", "open", "-l", "bug", "-A", "user", "-a", "assignee", "-S", "search", "-L", "1"],
        )
        assert result.exit_code == 0
        mock_client.get.assert_called_once()

    def test_json_fields(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "title": "T", "state": "open"}]
        result = runner.invoke(main, ["issue", "list", "--json", "number,title"])
        assert result.exit_code == 0
        assert '"number"' in result.output
        assert '"state"' not in result.output

    def test_jq(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "title": "T"}]
        result = runner.invoke(main, ["issue", "list", "-q", ".[0].number"])
        assert result.exit_code == 0

    def test_template(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "title": "T"}]
        result = runner.invoke(main, ["issue", "list", "-t", "{{.number}} {{.title}}"])
        assert result.exit_code == 0
        assert "1 T" in result.output

    def test_alias_ls(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "state": "open", "title": "T"}]
        result = runner.invoke(main, ["issue", "ls"])
        assert result.exit_code == 0
        assert "#1" in result.output


class TestIssueView:
    def test_default(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {
            "number": "42",
            "title": "Test",
            "body": "Body",
            "html_url": "https://ex.com/42",
        }
        result = runner.invoke(main, ["issue", "view", "42"])
        assert result.exit_code == 0
        assert "#42 Test" in result.output
        mock_client.get.assert_called_with("/repos/owner/repo/issues/42")

    def test_web(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "title": "Test", "html_url": "https://ex.com/42"}
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "view", "42", "-w"])
            assert result.exit_code == 0
            mock_browser.assert_called_once_with("https://ex.com/42")

    def test_url(self, runner, mock_client):
        mock_client.get.return_value = {"number": "42", "title": "Test", "body": "Body"}
        result = runner.invoke(main, ["issue", "view", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0
        mock_client.get.assert_called_with("/repos/owner/repo/issues/42")

    def test_json(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "title": "Test"}
        result = runner.invoke(main, ["issue", "view", "42", "--json", "number"])
        assert result.exit_code == 0
        assert '"number"' in result.output


class TestIssueCreate:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "create", "-t", "Test Title", "-b", "Body"])
        assert result.exit_code == 0
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert "/repos/owner/issues" in args[0]
        assert kwargs["json"]["title"] == "Test Title"

    def test_prompt_title(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "create", "-b", "Body"], input="Prompted Title\n")
        assert result.exit_code == 0
        assert "Prompted Title" in str(mock_client.post.call_args[1]["json"]["title"])

    def test_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("file body content")
        result = runner.invoke(main, ["issue", "create", "-t", "T", "-F", str(body_file)])
        assert result.exit_code == 0
        assert mock_client.post.call_args[1]["json"]["body"] == "file body content"

    def test_web(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "create", "-t", "T", "-w"])
            assert result.exit_code == 0
            mock_browser.assert_called_once()

    def test_alias_new(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "new", "-t", "T"])
        assert result.exit_code == 0
        mock_client.post.assert_called_once()

    def test_with_options(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "create", "-t", "T", "-a", "user", "-l", "bug", "-m", "v1.0"])
        assert result.exit_code == 0
        json_data = mock_client.post.call_args[1]["json"]
        assert json_data["assignee"] == "user"
        assert json_data["labels"] == "bug"
        assert json_data["milestone"] == "v1.0"


class TestIssueClose:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "close", "42"])
        assert result.exit_code == 0
        assert "Closed issue #42" in result.output
        mock_client.patch.assert_called_once()

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "close", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0
        mock_client.patch.assert_called_once()


class TestIssueComment:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "comment", "42", "-b", "hi"])
        assert result.exit_code == 0
        mock_client.post.assert_called_once()

    def test_prompt_body(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "comment", "42"], input="comment body\n")
        assert result.exit_code == 0
        assert "comment body" in str(mock_client.post.call_args[1]["json"]["body"])

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "comment", "https://gitcode.com/owner/repo/issues/42", "-b", "hi"])
        assert result.exit_code == 0


class TestIssueReopen:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "reopen", "42"])
        assert result.exit_code == 0
        assert "Reopened issue #42" in result.output
        mock_client.patch.assert_called_once()

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "reopen", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0


class TestIssueEdit:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "edit", "42", "-t", "New", "-b", "New body"])
        assert result.exit_code == 0
        assert "Edited issue #42" in result.output
        json_data = mock_client.patch.call_args[1]["json"]
        assert json_data["title"] == "New"
        assert json_data["body"] == "New body"

    def test_with_assignee_label(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "edit", "42", "-a", "user", "-l", "bug"])
        assert result.exit_code == 0
        json_data = mock_client.patch.call_args[1]["json"]
        assert json_data["assignee"] == "user"
        assert json_data["labels"] == "bug"

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "edit", "https://gitcode.com/owner/repo/issues/42", "-t", "New"])
        assert result.exit_code == 0


class TestIssueDelete:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "delete", "42"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted issue #42" in result.output
        mock_client.delete.assert_called_once()

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "delete", "https://gitcode.com/owner/repo/issues/42"], input="y\n")
        assert result.exit_code == 0


class TestIssueStatus:
    def test_default(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "state": "open", "title": "T"}]
        result = runner.invoke(main, ["issue", "status"])
        assert result.exit_code == 0
        assert "Relevant issues" in result.output
        mock_client.get.assert_called_once()
