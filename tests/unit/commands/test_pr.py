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
        return_value={"number": 42, "html_url": "https://example.com/42", "title": "Test", "head": {"ref": "feature"}}
    )
    client.patch = MagicMock(return_value={"number": 42, "html_url": "https://example.com/42", "title": "Test"})
    client.put = MagicMock(return_value={"message": "Merged"})
    client.delete = MagicMock(return_value=None)
    client.request = MagicMock(return_value="diff text")

    from gitcode_cli import context

    monkeypatch.setattr(context.AppContext, "client", lambda self: client)
    return client


@pytest.fixture
def mock_repo(monkeypatch):
    from gitcode_cli import repo

    monkeypatch.setattr(repo, "resolve_repo", lambda x=None: ("owner", "repo"))
    monkeypatch.setattr("gitcode_cli.commands.pr.resolve_repo", lambda x=None: ("owner", "repo"))


class TestPrList:
    def test_pr_list_default_renders_author_column(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "state": "open", "title": "First PR", "user": {"login": "alice"}},
        ]
        result = runner.invoke(main, ["pr", "list"])
        assert result.exit_code == 0
        assert "#1\topen\tFirst PR\talice" in result.output

    def test_pr_list_with_additional_compat_filters(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "state": "open", "title": "First PR"},
        ]
        result = runner.invoke(
            main,
            [
                "pr",
                "list",
                "-s",
                "open",
                "-A",
                "user",
                "-B",
                "master",
                "--assignee",
                "octocat",
                "--draft",
                "--head",
                "feature-branch",
                "-l",
                "bug",
                "-S",
                "search",
                "-L",
                "1",
            ],
        )
        assert result.exit_code == 0
        assert mock_client.get.call_args == call(
            "/repos/owner/repo/pulls",
            params={
                "state": "open",
                "author": "user",
                "base": "master",
                "assignee": "octocat",
                "draft": True,
                "head": "feature-branch",
                "labels": "bug",
                "search": "search",
            },
        )

    def test_pr_list_web_opens_pulls_page_without_fetch(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["pr", "list", "--web"])
        assert result.exit_code == 0
        mock_client.get.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/pulls")

    def test_pr_list_repeated_labels_are_normalized(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "state": "open", "title": "First PR"},
        ]
        result = runner.invoke(main, ["pr", "list", "-l", "bug", "-l", "docs"])
        assert result.exit_code == 0
        assert mock_client.get.call_args == call(
            "/repos/owner/repo/pulls",
            params={
                "state": None,
                "author": None,
                "base": None,
                "assignee": None,
                "draft": None,
                "head": None,
                "labels": "bug,docs",
                "search": None,
            },
        )

    def test_pr_list_rejects_value_for_draft_flag(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "list", "--draft", "true"])
        assert result.exit_code != 0
        assert "Got unexpected extra argument (true)" in result.output

    def test_pr_list_json(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "title": "First PR"},
        ]
        result = runner.invoke(main, ["pr", "list", "--json", "number,title"])
        assert result.exit_code == 0
        assert '"number": 1' in result.output
        assert '"title": "First PR"' in result.output

    def test_pr_list_template_with_json_uses_template(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "title": "First PR"},
            {"number": 2, "title": "Second PR"},
        ]
        result = runner.invoke(
            main,
            ["pr", "list", "--json", "number,title", "-t", "{{.number}} {{.title}}"],
        )
        assert result.exit_code == 0
        assert "1 First PR" in result.output
        assert "2 Second PR" in result.output
        assert '"number"' not in result.output

    def test_pr_list_alias_ls(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "state": "open", "title": "First PR"},
        ]
        result = runner.invoke(main, ["pr", "ls"])
        assert result.exit_code == 0
        assert "#1\topen\tFirst PR" in result.output

    def test_pr_list_help_shows_default_limit(self, runner):
        result = runner.invoke(main, ["pr", "list", "--help"])
        assert result.exit_code == 0
        assert "Maximum number of items to fetch." in result.output
        assert "[default:" in result.output

    def test_pr_view_renders_metadata_lines(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {
            "number": 42,
            "title": "Test PR",
            "state": "open",
            "body": "PR body",
            "user": {"login": "alice"},
            "head": {"label": "alice:feature"},
            "base": {"label": "owner:main"},
        }
        result = runner.invoke(main, ["pr", "view", "42"])
        assert result.exit_code == 0
        assert "Title:\tTest PR" in result.output
        assert "State:\topen" in result.output
        assert "Author:\talice" in result.output
        assert "Branch:\talice:feature -> owner:main" in result.output
        assert "Body:\nPR body" in result.output

    def test_pr_view_without_identifier_uses_current_branch(self, runner, mock_client, mock_repo):
        mock_client.get.side_effect = [
            [{"number": 42, "head": {"ref": "feature-branch"}, "title": "Branch PR"}],
            {"number": 42, "title": "Branch PR", "body": "Body text"},
        ]
        with patch(
            "gitcode_cli.commands.pr.resolve_pr_identifier_or_current_branch", return_value="feature-branch"
        ) as mock_resolver:
            result = runner.invoke(main, ["pr", "view"])
        assert result.exit_code == 0
        assert "#42 Branch PR" in result.output
        mock_resolver.assert_called_once_with(None)

    def test_pr_view_web(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.open_in_browser") as mock_browser:
            mock_client.get.return_value = {
                "number": 42,
                "title": "Test PR",
                "body": "",
                "html_url": "https://example.com/42",
            }
            result = runner.invoke(main, ["pr", "view", "42", "-w"])
            assert result.exit_code == 0
            mock_browser.assert_called_once_with("https://example.com/42")

    def test_pr_view_branch(self, runner, mock_client, mock_repo):
        mock_client.get.side_effect = [
            [{"number": 42, "head": {"ref": "feature-branch"}, "title": "Branch PR"}],
            {"number": 42, "title": "Branch PR", "body": "Body text"},
        ]
        result = runner.invoke(main, ["pr", "view", "feature-branch"])
        assert result.exit_code == 0
        assert "#42 Branch PR" in result.output


class TestPrCreate:
    def test_pr_create_help_documents_template_selection(self, runner):
        result = runner.invoke(main, ["pr", "create", "--help"])
        assert result.exit_code == 0
        assert "-T, --template" in result.output
        assert "Template file to use as the pull request body" in result.output

    def test_pr_create(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "https://example.com/42" in result.output
        assert mock_client.post.call_args.kwargs["json"]["title"] == "Test"
        assert mock_client.post.call_args.kwargs["json"]["body"] == "Body"
        assert mock_client.post.call_args.kwargs["json"]["base"] == "master"
        assert mock_client.post.call_args.kwargs["json"]["head"] == "feature"

    def test_pr_create_auto_detect(self, runner, mock_client, mock_repo):
        with (
            patch("gitcode_cli.commands.pr.get_current_git_branch", return_value="feature"),
            patch("gitcode_cli.commands.pr.get_default_base_branch", return_value="main"),
        ):
            result = runner.invoke(main, ["pr", "create", "--title", "Auto PR"])
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["head"] == "feature"
        assert mock_client.post.call_args.kwargs["json"]["base"] == "main"

    def test_pr_create_prompt_title(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            ["pr", "create", "--base", "master", "--head", "feature"],
            input="My Title\n",
        )
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["title"] == "My Title"

    def test_pr_create_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "body.txt"
        body_file.write_text("file body content")
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "-F", str(body_file), "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["body"] == "file body content"

    def test_pr_create_template_file_sets_body(self, runner, mock_client, mock_repo, tmp_path):
        template_file = tmp_path / "pull_request.md"
        template_file.write_text("template body content")
        result = runner.invoke(
            main,
            [
                "pr",
                "create",
                "--title",
                "Test",
                "--template",
                str(template_file),
                "--base",
                "master",
                "--head",
                "feature",
            ],
        )
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["body"] == "template body content"

    def test_pr_create_template_short_flag_sets_body(self, runner, mock_client, mock_repo, tmp_path):
        template_file = tmp_path / "pull_request.md"
        template_file.write_text("template body content")
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "-T", str(template_file), "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["body"] == "template body content"

    def test_pr_create_template_rejects_other_body_sources(self, runner, mock_client, mock_repo, tmp_path):
        template_file = tmp_path / "pull_request.md"
        template_file.write_text("template body content")
        result = runner.invoke(
            main,
            [
                "pr",
                "create",
                "--title",
                "Test",
                "--template",
                str(template_file),
                "--body",
                "inline",
                "--base",
                "master",
                "--head",
                "feature",
            ],
        )
        assert result.exit_code != 0
        assert "--template cannot be used with --body" in result.output
        mock_client.post.assert_not_called()

    def test_pr_create_missing_template_file_returns_click_error(self, runner, mock_client, mock_repo, tmp_path):
        missing = tmp_path / "missing.md"
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--template", str(missing), "--base", "master", "--head", "feature"],
        )
        assert result.exit_code != 0
        assert "Template file not found" in result.output
        mock_client.post.assert_not_called()

    def test_pr_create_uses_cli_compat_body_helper(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.get_body_from_options", return_value="resolved body") as mock_body:
            result = runner.invoke(main, ["pr", "create", "--title", "Test", "--head", "feature", "--base", "main"])
        assert result.exit_code == 0
        assert mock_body.call_args == call(body=None, body_file=None, editor=False)
        assert mock_client.post.call_args.kwargs["json"]["body"] == "resolved body"

    def test_pr_create_editor_uses_body_helper_with_editor(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.get_body_from_options", return_value="resolved body") as mock_body:
            result = runner.invoke(
                main, ["pr", "create", "--title", "Test", "--head", "feature", "--base", "main", "--editor"]
            )
        assert result.exit_code == 0
        assert mock_body.call_args == call(body=None, body_file=None, editor=True)
        assert mock_client.post.call_args.kwargs["json"]["body"] == "resolved body"

    def test_pr_create_dry_run_prints_normalized_payload_without_post(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            [
                "pr",
                "create",
                "--title",
                "Test",
                "--body",
                "Body",
                "--base",
                "master",
                "--head",
                "feature",
                "--dry-run",
                "-l",
                "bug",
                "-l",
                "docs",
                "-r",
                "alice",
                "-r",
                "bob",
                "-a",
                "carol",
                "-a",
                "dave",
                "--milestone",
                "v1",
            ],
        )
        assert result.exit_code == 0
        mock_client.post.assert_not_called()
        assert '"title": "Test"' in result.output
        assert '"body": "Body"' in result.output
        assert '"base": "master"' in result.output
        assert '"head": "feature"' in result.output
        assert '"labels": "bug,docs"' in result.output
        assert '"reviewers": "alice,bob"' in result.output
        assert '"assignees": "carol,dave"' in result.output
        assert '"milestone": "v1"' in result.output

    def test_pr_create_repeatable_people_and_labels_are_normalized(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            [
                "pr",
                "create",
                "--title",
                "Test",
                "--body",
                "Body",
                "--base",
                "master",
                "--head",
                "feature",
                "-l",
                "bug",
                "-l",
                "docs",
                "-r",
                "alice",
                "-r",
                "bob",
                "-a",
                "carol",
                "-a",
                "dave",
                "--milestone",
                "v1",
            ],
        )
        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["labels"] == "bug,docs"
        assert mock_client.post.call_args.kwargs["json"]["reviewers"] == "alice,bob"
        assert mock_client.post.call_args.kwargs["json"]["assignees"] == "carol,dave"
        assert mock_client.post.call_args.kwargs["json"]["milestone"] == "v1"

    def test_pr_create_alias_new(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            ["pr", "new", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "https://example.com/42" in result.output

    def test_pr_create_web_opens_create_page_without_post(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["pr", "create", "-w"])
        assert result.exit_code == 0
        mock_client.post.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/pulls/new")


class TestPrClose:
    def test_pr_close(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"number": 42, "head": {"ref": "feature"}}
        result = runner.invoke(main, ["pr", "close", "42"])
        assert result.exit_code == 0
        assert "Closed pull request #42" in result.output

    def test_pr_close_with_comment(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"number": 42, "head": {"ref": "feature"}}
        mock_client.post.return_value = {"id": 1}
        result = runner.invoke(main, ["pr", "close", "42", "-c", "closing comment"])
        assert result.exit_code == 0
        assert "Closed pull request #42" in result.output
        post_calls = [c for c in mock_client.post.call_args_list if "comments" in c.args[0]]
        assert len(post_calls) == 1
        assert post_calls[0].kwargs["json"]["body"] == "closing comment"

    def test_pr_close_delete_branch(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature"}}
            mock_client.patch.return_value = {"number": 42, "head": {"ref": "feature"}}
            result = runner.invoke(main, ["pr", "close", "42", "-d"])
            assert result.exit_code == 0
            assert "Deleted remote branch feature" in result.output
            assert "Closed pull request #42" in result.output
            mock_run.assert_called_once_with(
                ["git", "push", "origin", "--delete", "feature"],
                check=True,
            )

    def test_pr_close_delete_branch_help_mentions_remote_only(self, runner):
        result = runner.invoke(main, ["pr", "close", "--help"])
        assert result.exit_code == 0
        assert "Delete the remote branch after closing." in result.output
        assert "Delete the local and remote branch after closing." not in result.output

    def test_pr_close_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": 42, "head": {"ref": "feature"}}
        result = runner.invoke(main, ["pr", "close", "42"])
        assert result.exit_code == 0
        assert "Closed pull request #42" in result.output

    def test_pr_close_without_number_or_iid_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"state": "closed", "head": {"ref": "feature"}}
        result = runner.invoke(main, ["pr", "close", "42"])
        assert result.exit_code == 0
        assert "Closed pull request #42" in result.output


class TestPrMerge:
    def test_pr_merge(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42"])
        assert result.exit_code == 0
        assert "Merged" in result.output
        assert mock_client.put.call_args.kwargs["json"]["merge_method"] == "merge"

    def test_pr_merge_without_identifier_uses_current_branch(self, runner, mock_client, mock_repo):
        with patch(
            "gitcode_cli.commands.pr.resolve_pr_identifier_or_current_branch", return_value="42"
        ) as mock_resolver:
            result = runner.invoke(main, ["pr", "merge"])
        assert result.exit_code == 0
        assert "Merged" in result.output
        mock_resolver.assert_called_once_with(None)

    def test_pr_merge_squash(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "-s"])
        assert result.exit_code == 0
        assert "Merged" in result.output
        assert mock_client.put.call_args.kwargs["json"]["merge_method"] == "squash"

    def test_pr_merge_rebase(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "-r"])
        assert result.exit_code == 0
        assert "Merged" in result.output
        assert mock_client.put.call_args.kwargs["json"]["merge_method"] == "rebase"

    def test_pr_merge_rejects_mutually_exclusive_merge_flags(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "-m", "-s"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or "only one" in result.output.lower()
        mock_client.put.assert_not_called()

    def test_pr_merge_rejects_all_three_merge_flags(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "-m", "-s", "-r"])
        assert result.exit_code != 0
        mock_client.put.assert_not_called()

    def test_pr_merge_rebase_error_shows_clean_message(self, runner, mock_client, mock_repo):
        from gitcode_cli.errors import APIError

        mock_client.get.return_value = {"number": 42, "state": "open"}
        mock_client.put.side_effect = APIError("this patch has already been applied", status_code=405)
        result = runner.invoke(main, ["pr", "merge", "42", "-r"])
        assert result.exit_code != 0
        assert "this patch has already been applied" in result.output
        assert "Traceback" not in result.output

    def test_pr_merge_body_subject_and_admin_map_to_merge_payload(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            ["pr", "merge", "42", "--body", "Merge body", "--subject", "Merge subject", "--admin"],
        )
        assert result.exit_code == 0
        assert mock_client.put.call_args.kwargs["json"] == {
            "merge_method": "merge",
            "description": "Merge body",
            "title": "Merge subject",
            "force_merge": True,
        }

    def test_pr_merge_body_file_maps_to_description(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "merge-body.txt"
        body_file.write_text("file merge body")
        result = runner.invoke(main, ["pr", "merge", "42", "-F", str(body_file)])
        assert result.exit_code == 0
        assert mock_client.put.call_args.kwargs["json"]["description"] == "file merge body"

    def test_pr_merge_author_email_remains_unsupported(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "--author-email", "a@example.com"])
        assert result.exit_code != 0
        assert "does not support --author-email" in result.output
        mock_client.put.assert_not_called()

    def test_pr_merge_auto_remains_unsupported(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "merge", "42", "--auto"])
        assert result.exit_code != 0
        assert "does not support --auto" in result.output
        mock_client.put.assert_not_called()

    def test_pr_comment(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 123}
        result = runner.invoke(main, ["pr", "comment", "42", "--body", "hi"])
        assert result.exit_code == 0
        assert "123" in result.output

    def test_pr_comment_without_identifier_uses_current_branch(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 123}
        with patch(
            "gitcode_cli.commands.pr.resolve_pr_identifier_or_current_branch", return_value="42"
        ) as mock_resolver:
            result = runner.invoke(main, ["pr", "comment", "--body", "hi"])
        assert result.exit_code == 0
        assert "123" in result.output
        mock_resolver.assert_called_once_with(None)


class TestPrReview:
    def test_pr_review_approve_uses_requested_pr_number_when_review_response_lacks_number(
        self, runner, mock_client, mock_repo
    ):
        mock_client.post.return_value = {"id": 987, "body": "approved"}
        result = runner.invoke(main, ["pr", "review", "42", "--approve"])
        assert result.exit_code == 0
        assert "Reviewed pull request #42" in result.output

    def test_pr_review_without_identifier_uses_current_branch(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 987, "body": "approved"}
        with patch(
            "gitcode_cli.commands.pr.resolve_pr_identifier_or_current_branch", return_value="42"
        ) as mock_resolver:
            result = runner.invoke(main, ["pr", "review", "--approve"])
        assert result.exit_code == 0
        assert "Reviewed pull request #42" in result.output
        mock_resolver.assert_called_once_with(None)

    def test_pr_review_comment_uses_comment_api(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 123}
        result = runner.invoke(main, ["pr", "review", "42", "--comment", "--body", "Needs more tests"])
        assert result.exit_code == 0
        assert "Posted pull request comment 123" in result.output
        review_calls = [c for c in mock_client.post.call_args_list if "review" in c.args[0]]
        comment_calls = [c for c in mock_client.post.call_args_list if "comments" in c.args[0]]
        assert len(review_calls) == 0
        assert len(comment_calls) == 1
        assert comment_calls[0].kwargs["json"]["body"] == "Needs more tests"

    def test_pr_review_request_changes_downgrades_to_pr_comment_and_explains_it(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 456}
        result = runner.invoke(main, ["pr", "review", "42", "--request-changes", "--body", "Please address feedback"])
        assert result.exit_code != 0
        assert "Posted pull request comment 456" in result.output
        assert "does not support request-changes reviews" in result.output
        post_calls = [c for c in mock_client.post.call_args_list if "comments" in c.args[0]]
        assert len(post_calls) == 1
        assert post_calls[0].kwargs["json"]["body"] == "Please address feedback"

    def test_pr_review_requires_explicit_mode(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "review", "42"])
        assert result.exit_code != 0
        assert "Specify exactly one of --approve, --comment, or --request-changes." in result.output

    def test_pr_review_rejects_multiple_modes(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "review", "42", "--approve", "--comment"])
        assert result.exit_code != 0
        assert "Specify exactly one of --approve, --comment, or --request-changes." in result.output

    def test_pr_review_comment_requires_body(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "review", "42", "--comment"])
        assert result.exit_code != 0
        assert "Body is required when using --comment or --request-changes." in result.output

    def test_pr_review_comment_returns_zero_on_success(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 123}
        result = runner.invoke(main, ["pr", "review", "42", "--comment", "--body", "Needs more tests"])
        assert result.exit_code == 0
        assert "Posted pull request comment 123" in result.output

    def test_pr_review_request_changes_returns_nonzero_when_downgraded(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"id": 456}
        result = runner.invoke(main, ["pr", "review", "42", "--request-changes", "--body", "Please address feedback"])
        assert result.exit_code != 0
        assert "Posted pull request comment 456" in result.output

    def test_pr_review_comment_supports_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "review.txt"
        body_file.write_text("Needs more tests from file")
        mock_client.post.return_value = {"id": 123}
        result = runner.invoke(main, ["pr", "review", "42", "--comment", "-F", str(body_file)])
        assert result.exit_code == 0
        comment_calls = [c for c in mock_client.post.call_args_list if "comments" in c.args[0]]
        assert comment_calls[0].kwargs["json"]["body"] == "Needs more tests from file"

    def test_pr_review_request_changes_supports_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "review.txt"
        body_file.write_text("Please address feedback from file")
        mock_client.post.return_value = {"id": 456}
        result = runner.invoke(main, ["pr", "review", "42", "--request-changes", "-F", str(body_file)])
        assert result.exit_code != 0
        comment_calls = [c for c in mock_client.post.call_args_list if "comments" in c.args[0]]
        assert comment_calls[0].kwargs["json"]["body"] == "Please address feedback from file"

    def test_pr_review_approve_rejects_body(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "review", "42", "--approve", "--body", "LGTM"])
        assert result.exit_code != 0
        assert "does not support gh-style approval review body" in result.output
        mock_client.post.assert_not_called()

    def test_pr_review_approve_rejects_body_file(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "review.txt"
        body_file.write_text("LGTM from file")
        result = runner.invoke(main, ["pr", "review", "42", "--approve", "-F", str(body_file)])
        assert result.exit_code != 0
        assert "does not support gh-style approval review body" in result.output
        mock_client.post.assert_not_called()


class TestPrReopen:
    def test_pr_reopen(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"number": 42}
        result = runner.invoke(main, ["pr", "reopen", "42"])
        assert result.exit_code == 0
        assert "Reopened pull request #42" in result.output

    def test_pr_reopen_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": 42}
        result = runner.invoke(main, ["pr", "reopen", "42"])
        assert result.exit_code == 0
        assert "Reopened pull request #42" in result.output


class TestPrEdit:
    def test_pr_edit(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"number": 42}
        result = runner.invoke(main, ["pr", "edit", "42", "-t", "New", "-B", "develop"])
        assert result.exit_code == 0
        assert "Edited pull request #42" in result.output
        assert mock_client.patch.call_args.kwargs["json"]["title"] == "New"
        assert mock_client.patch.call_args.kwargs["json"]["base"] == "develop"

    def test_pr_edit_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": 42}
        result = runner.invoke(main, ["pr", "edit", "42", "-t", "New"])
        assert result.exit_code == 0
        assert "Edited pull request #42" in result.output


class TestPrStatus:
    def test_pr_status_shows_single_approximation_section(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = [
            {"number": 1, "state": "open", "title": "First PR"},
        ]
        result = runner.invoke(main, ["pr", "status"])
        assert result.exit_code == 0
        # Single header with GitCode approximation disclaimer
        assert "Open pull requests in owner/repo" in result.output
        assert "GitCode API approximation" in result.output
        assert "user-specific filtering is not available" in result.output
        # PR is listed once
        assert result.output.count("#1\topen\tFirst PR") == 1
        # Old misleading headings must NOT appear
        assert "Current branch" not in result.output
        assert "Created by you" not in result.output
        assert "Requesting your review" not in result.output

    def test_pr_status_empty_list(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = []
        result = runner.invoke(main, ["pr", "status"])
        assert result.exit_code == 0
        assert "No open pull requests" in result.output


class TestPrDiff:
    def test_pr_diff(self, runner, mock_client, mock_repo):
        mock_client.request.return_value = "diff text"
        result = runner.invoke(main, ["pr", "diff", "42"])
        assert result.exit_code == 0
        assert "diff text" in result.output


class TestPrCheckout:
    def test_pr_checkout(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code == 0
            assert "Checked out branch feature-branch" in result.output
            # fetch, rev-parse (branch doesn't exist), checkout -b
            assert mock_run.call_count == 3
            mock_run.assert_any_call(
                ["git", "fetch", "origin", "feature-branch"],
                check=True,
            )
            mock_run.assert_any_call(
                ["git", "checkout", "-b", "feature-branch", "origin/feature-branch"],
                check=True,
            )

    def test_pr_checkout_existing_branch_with_correct_tracking(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            # rev-parse succeeds (branch exists), for-each-ref shows correct tracking
            mock_run.side_effect = [
                MagicMock(),  # fetch
                MagicMock(returncode=0),  # rev-parse — branch exists
                MagicMock(stdout="origin/feature-branch"),  # for-each-ref — correct tracking
                MagicMock(),  # checkout
            ]
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code == 0
            assert "Checked out existing branch feature-branch (tracking origin/feature-branch)" in result.output

    def test_pr_checkout_existing_branch_with_wrong_tracking(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            mock_run.side_effect = [
                MagicMock(),  # fetch
                MagicMock(returncode=0),  # rev-parse — branch exists
                MagicMock(stdout="origin/other-branch"),  # for-each-ref — wrong tracking
            ]
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code != 0
            assert "already exists" in result.output
            assert "does not track" in result.output

    def test_pr_checkout_custom_branch_existing_with_correct_tracking(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            mock_run.side_effect = [
                MagicMock(),  # fetch
                MagicMock(returncode=0),  # rev-parse — custom branch exists
                MagicMock(stdout="origin/feature-branch"),  # for-each-ref — correct tracking
                MagicMock(),  # checkout
            ]
            result = runner.invoke(main, ["pr", "checkout", "42", "-b", "my-local-feature"])
            assert result.exit_code == 0
            assert "Checked out existing branch my-local-feature" in result.output

    def test_pr_checkout_ignores_matching_tag_when_local_branch_does_not_exist(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            mock_run.side_effect = [
                MagicMock(),  # fetch
                MagicMock(returncode=1),  # refs/heads/feature-branch does not exist
                MagicMock(),  # checkout -b
            ]
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code == 0
            mock_run.assert_any_call(
                ["git", "rev-parse", "--verify", "refs/heads/feature-branch"],
                capture_output=True,
                text=True,
                check=False,
            )
            mock_run.assert_any_call(
                ["git", "checkout", "-b", "feature-branch", "origin/feature-branch"],
                check=True,
            )

    def test_pr_checkout_existing_branch_checkout_failure_is_wrapped(self, runner, mock_client, mock_repo):
        import subprocess

        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_client.get.return_value = {"number": 42, "head": {"ref": "feature-branch"}}
            mock_run.side_effect = [
                MagicMock(),  # fetch
                MagicMock(returncode=0),  # rev-parse — branch exists
                MagicMock(stdout="origin/feature-branch"),  # tracking matches
                subprocess.CalledProcessError(1, ["git", "checkout", "feature-branch"]),
            ]
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code != 0
            assert "Git checkout failed" in result.output


class TestPrReady:
    def test_pr_ready(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"number": 42}
        result = runner.invoke(main, ["pr", "ready", "42"])
        assert result.exit_code == 0
        assert "Marked pull request #42 as ready for review" in result.output

    def test_pr_ready_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": 42}
        result = runner.invoke(main, ["pr", "ready", "42"])
        assert result.exit_code == 0
        assert "Marked pull request #42 as ready for review" in result.output

    def test_pr_ready_undo_without_number_in_response(self, runner, mock_client, mock_repo):
        mock_client.patch.return_value = {"iid": 42}
        result = runner.invoke(main, ["pr", "ready", "42", "--undo"])
        assert result.exit_code == 0
        assert "Converted pull request #42 to draft" in result.output


class TestPrCreateEdgeCases:
    def test_create_no_head_detect_fails(self, runner, mock_client, mock_repo, monkeypatch):
        from gitcode_cli import commands

        monkeypatch.setattr(commands.pr, "get_current_git_branch", lambda: None)
        result = runner.invoke(main, ["pr", "create", "-t", "T", "-B", "master"])
        assert result.exit_code != 0
        assert "Unable to detect current branch" in result.output

    def test_create_web(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.pr.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["pr", "create", "-t", "T", "-B", "master", "-H", "feature", "-w"])
            assert result.exit_code == 0
            mock_browser.assert_called_once()

    def test_pr_create_rejects_body_and_body_file_together(self, runner, mock_client, mock_repo, tmp_path):
        body_file = tmp_path / "body.txt"
        body_file.write_text("file body")
        result = runner.invoke(
            main,
            [
                "pr",
                "create",
                "-t",
                "Test",
                "-b",
                "inline body",
                "-F",
                str(body_file),
                "--base",
                "master",
                "--head",
                "feature",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()
        mock_client.post.assert_not_called()


class TestPrCloseEdgeCases:
    def test_close_delete_branch_no_ref(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": 42, "head": {}}
        mock_client.patch.return_value = {"number": 42, "head": {}}
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            result = runner.invoke(main, ["pr", "close", "42", "-d"])
            assert result.exit_code == 0
            assert "Warning: could not determine branch to delete" in result.output
            mock_run.assert_not_called()

    def test_close_delete_branch_git_fails(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": 42, "head": {"ref": "feature"}}
        mock_client.patch.return_value = {"number": 42, "head": {"ref": "feature"}}
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("git failed")
            result = runner.invoke(main, ["pr", "close", "42", "-d"])
            assert result.exit_code == 0
            assert "Warning: could not delete remote branch" in result.output

    def test_close_delete_branch_fetches_pr_before_close(self, runner, mock_client, mock_repo):
        """When close response lacks head.ref, we should have fetched it beforehand."""
        mock_client.get.return_value = {"number": 42, "head": {"ref": "feature"}}
        mock_client.patch.return_value = {"number": 42, "head": {}}
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            result = runner.invoke(main, ["pr", "close", "42", "-d"])
            assert result.exit_code == 0
            assert "Deleted remote branch feature" in result.output
            mock_run.assert_called_once_with(
                ["git", "push", "origin", "--delete", "feature"],
                check=True,
            )


class TestPrReviewEdgeCases:
    def test_review_no_mode(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["pr", "review", "42"])
        assert result.exit_code != 0
        assert "Specify exactly one of --approve, --comment, or --request-changes." in result.output


class TestPrCheckoutEdgeCases:
    def test_checkout_no_head_ref(self, runner, mock_client, mock_repo):
        mock_client.get.return_value = {"number": 42, "head": {}}
        result = runner.invoke(main, ["pr", "checkout", "42"])
        assert result.exit_code != 0
        assert "Unable to determine PR branch" in result.output

    def test_checkout_git_fails(self, runner, mock_client, mock_repo):
        import subprocess

        mock_client.get.return_value = {"number": 42, "head": {"ref": "feature"}}
        with patch("gitcode_cli.commands.pr.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["git", "fetch"])
            result = runner.invoke(main, ["pr", "checkout", "42"])
            assert result.exit_code != 0
            assert "Git fetch failed" in result.output


class TestPrCreateMissingHtmlUrl:
    def test_pr_create_missing_html_url_falls_back_to_url(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"number": 42, "url": "https://api.example.com/42", "title": "Test"}
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "https://api.example.com/42" in result.output

    def test_pr_create_missing_html_url_and_url_falls_back_to_number(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"number": 42, "title": "Test"}
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "Created PR #42" in result.output

    def test_pr_create_with_html_url_unchanged(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"number": 42, "html_url": "https://example.com/42", "title": "Test"}
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "https://example.com/42" in result.output

    def test_pr_create_missing_all_url_fields_falls_back_to_generic_message(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"title": "Test"}
        result = runner.invoke(
            main,
            ["pr", "create", "--title", "Test", "--body", "Body", "--base", "master", "--head", "feature"],
        )
        assert result.exit_code == 0
        assert "Created pull request" in result.output
