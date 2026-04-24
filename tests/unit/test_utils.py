"""Tests for gitcode_cli.utils module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest

from gitcode_cli.utils import (
    get_current_git_branch,
    get_default_git_branch,
    open_in_browser,
    parse_issue_url,
    parse_pr_url,
    prompt_if_missing,
    read_body_file,
    resolve_issue_arg,
    resolve_pr_arg,
)


class TestPromptIfMissing:
    def test_returns_value_when_present(self):
        assert prompt_if_missing("hello", "Enter value") == "hello"

    def test_prompts_when_missing(self, monkeypatch):
        mock_prompt = MagicMock(return_value="typed")
        monkeypatch.setattr("gitcode_cli.utils.click.prompt", mock_prompt)
        result = prompt_if_missing(None, "Enter value")
        assert result == "typed"
        mock_prompt.assert_called_once_with("Enter value", hide_input=False)

    def test_prompts_when_empty_string(self, monkeypatch):
        mock_prompt = MagicMock(return_value="typed")
        monkeypatch.setattr("gitcode_cli.utils.click.prompt", mock_prompt)
        result = prompt_if_missing("", "Enter value", hide_input=True)
        assert result == "typed"
        mock_prompt.assert_called_once_with("Enter value", hide_input=True)


class TestGetCurrentGitBranch:
    @patch("gitcode_cli.utils.subprocess.run")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="feature-branch\n")
        assert get_current_git_branch() == "feature-branch"

    @patch("gitcode_cli.utils.subprocess.run")
    def test_failure(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        assert get_current_git_branch() is None


class TestGetDefaultGitBranch:
    @patch("gitcode_cli.utils.subprocess.run")
    def test_success_with_origin_prefix(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="origin/main\n")
        assert get_default_git_branch() == "main"

    @patch("gitcode_cli.utils.subprocess.run")
    def test_success_without_origin_prefix(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="master\n")
        assert get_default_git_branch() == "master"

    @patch("gitcode_cli.utils.subprocess.run")
    def test_failure_returns_none(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        assert get_default_git_branch() is None


class TestReadBodyFile:
    def test_reads_file_content(self, tmp_path: Path):
        file_path = tmp_path / "body.md"
        file_path.write_text("Hello world")
        assert read_body_file(str(file_path)) == "Hello world"

    def test_reads_unicode_content(self, tmp_path: Path):
        file_path = tmp_path / "body.md"
        file_path.write_text("Hello 世界", encoding="utf-8")
        assert read_body_file(str(file_path)) == "Hello 世界"


class TestOpenInBrowser:
    @patch("gitcode_cli.utils.webbrowser.open")
    def test_opens_url(self, mock_open: MagicMock):
        open_in_browser("https://gitcode.com")
        mock_open.assert_called_once_with("https://gitcode.com")


class TestParseIssueUrl:
    def test_match(self):
        result = parse_issue_url("https://gitcode.com/owner/repo/issues/42")
        assert result == ("owner", "repo", "42")

    def test_match_http(self):
        result = parse_issue_url("http://gitcode.com/owner/repo/issues/1")
        assert result == ("owner", "repo", "1")

    def test_no_match_pr_url(self):
        assert parse_issue_url("https://gitcode.com/owner/repo/pulls/42") is None

    def test_no_match_random_url(self):
        assert parse_issue_url("https://example.com/something") is None

    def test_no_match_none(self):
        assert parse_issue_url("not-a-url") is None

    def test_whitespace_stripped(self):
        result = parse_issue_url("  https://gitcode.com/owner/repo/issues/5  ")
        assert result == ("owner", "repo", "5")


class TestParsePrUrl:
    def test_match_pull(self):
        result = parse_pr_url("https://gitcode.com/owner/repo/pull/42")
        assert result == ("owner", "repo", "42")

    def test_match_pulls(self):
        result = parse_pr_url("https://gitcode.com/owner/repo/pulls/42")
        assert result == ("owner", "repo", "42")

    def test_match_http(self):
        result = parse_pr_url("http://gitcode.com/owner/repo/pull/1")
        assert result == ("owner", "repo", "1")

    def test_no_match_issue_url(self):
        assert parse_pr_url("https://gitcode.com/owner/repo/issues/42") is None

    def test_no_match_random_url(self):
        assert parse_pr_url("https://example.com/something") is None

    def test_whitespace_stripped(self):
        result = parse_pr_url("  https://gitcode.com/owner/repo/pull/5  ")
        assert result == ("owner", "repo", "5")


class TestResolveIssueArg:
    def test_number(self):
        assert resolve_issue_arg("42") == (None, None, "42")

    def test_url(self):
        assert resolve_issue_arg("https://gitcode.com/owner/repo/issues/42") == (
            "owner",
            "repo",
            "42",
        )

    def test_arbitrary_string(self):
        assert resolve_issue_arg("abc") == (None, None, "abc")


class TestResolvePrArg:
    def test_number(self):
        assert resolve_pr_arg("42", "owner", "repo", MagicMock()) == ("owner", "repo", "42")

    def test_url(self):
        assert resolve_pr_arg("https://gitcode.com/owner/repo/pull/42", "other", "other-repo", MagicMock()) == (
            "owner",
            "repo",
            "42",
        )
