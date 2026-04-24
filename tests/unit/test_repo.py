"""Tests for gitcode_cli.repo module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from gitcode_cli.errors import RepoResolutionError
from gitcode_cli.repo import parse_remote_url, parse_repo, resolve_repo


class TestParseRepo:
    def test_two_parts(self):
        assert parse_repo("owner/repo") == ("owner", "repo")

    def test_two_parts_with_dashes(self):
        assert parse_repo("my-owner/my-repo") == ("my-owner", "my-repo")

    def test_three_parts(self):
        assert parse_repo("gitcode.com/owner/repo") == ("owner", "repo")

    def test_three_parts_with_host(self):
        assert parse_repo("github.com/owner/repo-name") == ("owner", "repo-name")

    def test_invalid_one_part(self):
        with pytest.raises(RepoResolutionError, match="Invalid repo format"):
            parse_repo("repo")

    def test_invalid_four_parts(self):
        with pytest.raises(RepoResolutionError, match="Invalid repo format"):
            parse_repo("a/b/c/d")


class TestParseRemoteUrl:
    def test_https_url(self):
        assert parse_remote_url("https://gitcode.com/owner/repo.git") == ("owner", "repo")

    def test_https_url_without_git(self):
        assert parse_remote_url("https://gitcode.com/owner/repo") == ("owner", "repo")

    def test_http_url(self):
        assert parse_remote_url("http://gitcode.com/owner/repo.git") == ("owner", "repo")

    def test_ssh_url(self):
        assert parse_remote_url("git@gitcode.com:owner/repo.git") == ("owner", "repo")

    def test_ssh_url_without_git(self):
        assert parse_remote_url("git@gitcode.com:owner/repo") == ("owner", "repo")

    def test_invalid_url(self):
        with pytest.raises(RepoResolutionError, match="Unsupported remote URL"):
            parse_remote_url("ftp://gitcode.com/owner/repo")

    def test_ssh_url_with_whitespace(self):
        assert parse_remote_url("  git@gitcode.com:owner/repo.git  ") == ("owner", "repo")


class TestResolveRepo:
    def test_explicit_repo(self):
        assert resolve_repo("owner/repo") == ("owner", "repo")

    def test_explicit_repo_three_parts(self):
        assert resolve_repo("host/owner/repo") == ("owner", "repo")

    @patch("gitcode_cli.repo.subprocess.run")
    def test_fallback_to_git_remote_https(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="https://gitcode.com/owner/repo.git\n")
        assert resolve_repo() == ("owner", "repo")
        mock_run.assert_called_once_with(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("gitcode_cli.repo.subprocess.run")
    def test_fallback_to_git_remote_ssh(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="git@gitcode.com:owner/repo.git")
        assert resolve_repo() == ("owner", "repo")

    @patch("gitcode_cli.repo.subprocess.run")
    def test_git_failure_raises_repo_resolution_error(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        with pytest.raises(RepoResolutionError, match="Unable to infer repo"):
            resolve_repo()

    @patch("gitcode_cli.repo.subprocess.run")
    def test_git_failure_has_cause(self, mock_run: MagicMock):
        exc = subprocess.CalledProcessError(1, "git")
        mock_run.side_effect = exc
        with pytest.raises(RepoResolutionError) as ctx:
            resolve_repo()
        assert ctx.value.__cause__ is exc
