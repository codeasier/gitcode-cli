"""Tests for gitcode_cli.commands.issue."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

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
    import gitcode_cli.commands.issue as issue_mod

    monkeypatch.setattr(issue_mod, "resolve_repo", lambda x=None: ("owner", "repo"))


class TestIssueList:
    def test_default_renders_author_in_list_output(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": "1", "state": "open", "title": "First", "author": {"login": "alice"}},
            {"number": "2", "state": "closed", "title": "Second"},
        ]
        result = runner.invoke(main, ["issue", "list"])
        assert result.exit_code == 0
        assert "#1\topen\tFirst\talice" in result.output
        assert "#2\tclosed\tSecond\t" in result.output
        mock_client.get.assert_called_once()

    def test_with_options(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            [
                "issue",
                "list",
                "-s",
                "open",
                "-l",
                "bug",
                "-l",
                "help wanted",
                "-A",
                "user",
                "-a",
                "assignee",
                "-S",
                "search",
                "--milestone",
                "v1",
                "--mention",
                "octocat",
                "-L",
                "1",
            ],
        )
        assert result.exit_code == 0
        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/issues",
            params={
                "state": "open",
                "labels": "bug,help wanted",
                "creator": "user",
                "assignee": "assignee",
                "search": "search",
                "milestone": "v1",
                "mention": "octocat",
            },
        )

    def test_web_opens_issues_page_without_fetching(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "list", "--web"])
        assert result.exit_code == 0
        mock_client.get.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues")

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

    def test_list_help_shows_default_limit(self, runner):
        result = runner.invoke(main, ["issue", "list", "--help"])
        assert result.exit_code == 0
        assert "Maximum number of items to fetch." in result.output
        assert "[default:" in result.output

    def test_rejects_zero_limit(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output
        mock_client.get.assert_not_called()


class TestIssueView:
    def test_default_renders_metadata_lines(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {
            "number": "42",
            "title": "Test",
            "state": "open",
            "author": {"login": "alice"},
            "body": "Body",
            "html_url": "https://ex.com/42",
        }
        result = runner.invoke(main, ["issue", "view", "42"])
        assert result.exit_code == 0
        assert "Title:\tTest" in result.output
        assert "State:\topen" in result.output
        assert "Author:\talice" in result.output
        assert "Body:\nBody" in result.output
        mock_client.get.assert_called_with("/repos/owner/repo/issues/42")

    def test_web_uses_derived_issue_url_without_fetching(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "view", "42", "-w"])
        assert result.exit_code == 0
        mock_client.get.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues/42")

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

    def test_comments_json_includes_comments(self, runner, mock_client, mock_repo):
        mock_client.get.side_effect = [
            {"number": "42", "title": "Test", "body": "Body", "html_url": "https://ex.com/42"},
            [
                {"id": 1, "body": "First comment"},
                {"id": 2, "body": "Second comment"},
            ],
        ]
        result = runner.invoke(main, ["issue", "view", "42", "--comments", "--json", "number,comments"])
        assert result.exit_code == 0
        assert '"number": "42"' in result.output
        assert '"comments"' in result.output
        assert '"First comment"' in result.output
        assert '"Second comment"' in result.output
        assert mock_client.get.call_args_list == [
            call("/repos/owner/repo/issues/42"),
            call("/repos/owner/repo/issues/42/comments"),
        ]

    def test_comments_default_keeps_metadata_and_comments(self, runner, mock_client, mock_repo):
        mock_client.get.side_effect = [
            {
                "number": "42",
                "title": "Test",
                "state": "open",
                "author": {"login": "alice"},
                "body": "Body",
                "html_url": "https://ex.com/42",
            },
            [
                {"id": 1, "body": "First comment"},
                {"id": 2, "body": "Second comment"},
            ],
        ]
        result = runner.invoke(main, ["issue", "view", "42", "--comments"])
        assert result.exit_code == 0
        assert "Title:\tTest" in result.output
        assert "Comments:" in result.output
        assert "- First comment" in result.output
        assert "- Second comment" in result.output

    def test_rejects_non_numeric_identifier(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "view", "not-a-number"])
        assert result.exit_code != 0
        assert "Issue identifier must be a number or a valid issue URL." in result.output
        mock_client.get.assert_not_called()

    def test_not_found_returns_friendly_error(self, runner, mock_client, mock_repo):
        from gitcode_cli.errors import APIError

        mock_client.get.side_effect = APIError("Issue not found", 404)
        result = runner.invoke(main, ["issue", "view", "42"])
        assert result.exit_code != 0
        assert "error: Issue not found" in result.output
        assert "Traceback" not in result.output

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

    def test_reads_body_from_stdin_when_body_file_is_dash(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "create", "-t", "T", "-F", "-"], input="stdin body")
        assert result.exit_code == 0
        assert mock_client.post.call_args[1]["json"]["body"] == "stdin body"

    def test_rejects_body_and_body_file_together(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("file body content")
        result = runner.invoke(main, ["issue", "create", "-t", "T", "-b", "inline", "-F", str(body_file)])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()
        mock_client.post.assert_not_called()

    def test_missing_body_file_returns_click_error(self, runner, mock_client, mock_repo, tmp_path):
        missing = tmp_path / "missing.md"
        result = runner.invoke(main, ["issue", "create", "-t", "T", "-F", str(missing)])
        assert result.exit_code != 0
        assert "Body file not found" in result.output
        mock_client.post.assert_not_called()

    def test_rejects_title_longer_than_255_characters(self, runner, mock_client, mock_repo):
        title = "T" * 256
        result = runner.invoke(main, ["issue", "create", "-t", title])
        assert result.exit_code != 0
        assert "title must be 255 characters or fewer" in result.output
        mock_client.post.assert_not_called()

    def test_web(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "create", "-t", "T", "-w"])
            assert result.exit_code == 0
            mock_browser.assert_called_once()

    def test_web_opens_create_page_without_post(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "create", "-t", "T", "--web"])
        assert result.exit_code == 0
        mock_client.post.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues/new")

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
        mock_client.get.return_value = {"number": "42", "state": "open"}
        result = runner.invoke(main, ["issue", "close", "42"])
        assert result.exit_code == 0
        assert "Closed issue #42" in result.output
        mock_client.patch.assert_called_once()

    def test_url(self, runner, mock_client):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        result = runner.invoke(main, ["issue", "close", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0
        mock_client.patch.assert_called_once()

    def test_close_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        mock_client.patch.return_value = {"iid": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42"])
        assert result.exit_code == 0
        assert "Closed issue #42" in result.output

    def test_close_without_number_or_iid_in_response(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        mock_client.patch.return_value = {"state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42"])
        assert result.exit_code == 0
        assert "Closed issue #42" in result.output


class TestIssueCloseIdempotency:
    def test_close_already_closed_issue_is_idempotent(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42"])
        assert result.exit_code == 0
        assert "already closed" in result.output.lower()
        mock_client.patch.assert_not_called()
        mock_client.post.assert_not_called()

    def test_close_already_closed_issue_still_posts_explicit_comment(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42", "-c", "done"])
        assert result.exit_code == 0
        assert "already closed; posted comment" in result.output.lower()
        mock_client.post.assert_called_once()
        mock_client.patch.assert_not_called()

    def test_close_with_comment_and_reason(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        mock_client.patch.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42", "-c", "done", "-r", "completed"])
        assert result.exit_code == 0
        assert "Closed issue" in result.output
        post_calls = [c for c in mock_client.post.call_args_list if "comments" in str(c)]
        assert len(post_calls) == 1

    def test_close_with_reason_sends_state_close_and_state_reason(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        mock_client.patch.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "close", "42", "-r", "completed"])
        assert result.exit_code == 0
        patch_kwargs = mock_client.patch.call_args.kwargs
        assert patch_kwargs["json"]["state"] == "close"
        assert patch_kwargs["json"]["state_reason"] == "completed"


class TestIssueComment:
    def test_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "comment", "42", "-b", "hi"])
        assert result.exit_code == 0
        mock_client.post.assert_called_once()

    def test_prompt_body(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "comment", "42"], input="comment body\n")
        assert result.exit_code == 0
        assert "comment body" in str(mock_client.post.call_args[1]["json"]["body"])

    def test_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "comment.md"
        body_file.write_text("file comment")
        result = runner.invoke(main, ["issue", "comment", "42", "-F", str(body_file)])
        assert result.exit_code == 0
        assert mock_client.post.call_args[1]["json"]["body"] == "file comment"

    def test_editor(self, runner, mock_client, mock_repo, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.issue.get_body_from_options", lambda **kwargs: "edited comment")
        result = runner.invoke(main, ["issue", "comment", "42", "-e"])
        assert result.exit_code == 0
        assert mock_client.post.call_args[1]["json"]["body"] == "edited comment"

    def test_editor_cancel_returns_error(self, runner, mock_client, mock_repo, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.issue.get_body_from_options", lambda **kwargs: None)
        result = runner.invoke(main, ["issue", "comment", "42", "-e"])
        assert result.exit_code != 0
        assert "Editor was closed without saving a comment." in result.output
        mock_client.post.assert_not_called()

    def test_web_opens_issue_page_without_posting(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "comment", "42", "--web"])
        assert result.exit_code == 0
        mock_client.post.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues/42")

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "comment", "https://gitcode.com/owner/repo/issues/42", "-b", "hi"])
        assert result.exit_code == 0


class TestIssueReopen:
    def test_default(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "reopen", "42"])
        assert result.exit_code == 0
        assert "Reopened issue #42" in result.output
        mock_client.patch.assert_called_once()

    def test_url(self, runner, mock_client):
        mock_client.get.return_value = {"number": "42", "state": "closed"}
        result = runner.invoke(main, ["issue", "reopen", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0

    def test_reopen_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "closed"}
        mock_client.patch.return_value = {"iid": "42", "state": "open"}
        result = runner.invoke(main, ["issue", "reopen", "42"])
        assert result.exit_code == 0
        assert "Reopened issue #42" in result.output


class TestIssueReopenIdempotency:
    def test_reopen_already_open_issue_is_idempotent(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": "42", "state": "open"}
        result = runner.invoke(main, ["issue", "reopen", "42"])
        assert result.exit_code == 0
        assert "already open" in result.output.lower()
        mock_client.patch.assert_not_called()


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

    def test_supports_multiple_labels(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "edit", "42", "-l", "bug", "-l", "docs"])
        assert result.exit_code == 0
        json_data = mock_client.patch.call_args[1]["json"]
        assert json_data["labels"] == "bug,docs"

    def test_body_and_body_file_are_mutually_exclusive(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("file body")
        result = runner.invoke(main, ["issue", "edit", "42", "-b", "inline body", "-F", str(body_file)])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()
        mock_client.patch.assert_not_called()

    def test_body_file_can_read_from_stdin(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "edit", "42", "-F", "-"], input="stdin body\n")
        assert result.exit_code == 0
        assert mock_client.patch.call_args[1]["json"]["body"] == "stdin body\n"

    def test_rejects_empty_edit(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["issue", "edit", "42"])
        assert result.exit_code != 0
        assert "must specify at least one field to edit" in result.output
        mock_client.patch.assert_not_called()

    def test_url(self, runner, mock_client):
        result = runner.invoke(main, ["issue", "edit", "https://gitcode.com/owner/repo/issues/42", "-t", "New"])
        assert result.exit_code == 0

    def test_edit_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": "42", "title": "New"}
        result = runner.invoke(main, ["issue", "edit", "42", "-t", "New"])
        assert result.exit_code == 0
        assert "Edited issue #42" in result.output


class TestIssueDelete:
    def test_default(self, runner, mock_client, mock_repo, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.issue._stdin_is_tty", lambda: True)
        monkeypatch.setattr("gitcode_cli.commands.issue.click.confirm", lambda *args, **kwargs: True)
        result = runner.invoke(main, ["issue", "delete", "42"])
        assert result.exit_code == 0
        assert "Deleted issue #42" in result.output
        mock_client.delete.assert_called_once()

    def test_url(self, runner, mock_client, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.issue._stdin_is_tty", lambda: True)
        monkeypatch.setattr("gitcode_cli.commands.issue.click.confirm", lambda *args, **kwargs: True)
        result = runner.invoke(main, ["issue", "delete", "https://gitcode.com/owner/repo/issues/42"])
        assert result.exit_code == 0

    def test_non_tty_stdin_returns_clear_error(self, runner, mock_client, mock_repo, monkeypatch):
        monkeypatch.setattr("gitcode_cli.commands.issue._stdin_is_tty", lambda: False)
        result = runner.invoke(main, ["issue", "delete", "42"])
        assert result.exit_code != 0
        assert "Cannot prompt for confirmation when stdin is not a TTY." in result.output
        mock_client.delete.assert_not_called()


class TestIssueDevelop:
    def test_develop_opens_browser(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "develop", "42"])
        assert result.exit_code == 0
        assert "does not create a local branch" in result.output
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues/42")

    def test_develop_help(self, runner):
        result = runner.invoke(main, ["issue", "develop", "--help"])
        assert result.exit_code == 0
        assert "Base branch for the develop branch." in result.output
        assert "Name for the local branch." in result.output

    @pytest.mark.parametrize(
        "args",
        [
            ["--base", "main"],
            ["--name", "feature-42"],
            ["--base", "main", "--name", "feature-42"],
        ],
    )
    def test_rejects_unimplemented_branch_options(self, runner, mock_client, mock_repo, args):
        with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["issue", "develop", "42", *args])

        assert result.exit_code != 0
        assert "--base and --name are not supported" in result.output
        mock_browser.assert_not_called()


class TestIssueStatus:
    def test_default(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [{"number": "1", "state": "open", "title": "T"}]
        result = runner.invoke(main, ["issue", "status"])
        assert result.exit_code == 0
        assert "GitCode-limited approximation" in result.output
        assert "Repository open issues" in result.output
        mock_client.get.assert_called_once()

    def test_lists_repository_open_issues_with_limited_wording(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {
                "number": "1",
                "state": "open",
                "title": "Mine",
                "author": {"login": "alice"},
                "assignee": {"login": "alice"},
            },
            {"number": "2", "state": "open", "title": "Other", "author": {"login": "bob"}},
        ]
        result = runner.invoke(main, ["issue", "status"])
        assert result.exit_code == 0
        assert "GitCode-limited approximation" in result.output
        assert "Repository open issues" in result.output
        assert "#1" in result.output
        assert "#2" in result.output
