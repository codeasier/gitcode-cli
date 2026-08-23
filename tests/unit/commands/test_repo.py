"""Tests for gitcode_cli.commands.repo."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.errors import APIError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.get = MagicMock(return_value=[])
    client.post = MagicMock(return_value={})
    client.patch = MagicMock(return_value={})
    client.put = MagicMock(return_value={})
    client.delete = MagicMock(return_value=None)

    from gitcode_cli import context

    monkeypatch.setattr(context.AppContext, "client", lambda self: client)
    return client


@pytest.fixture
def mock_repo(monkeypatch):
    import gitcode_cli.commands.repo as repo_mod
    from gitcode_cli import repo

    monkeypatch.setattr(repo, "resolve_repo", lambda x=None: ("owner", "repo"))
    monkeypatch.setattr(repo_mod, "resolve_repo", lambda x=None: ("owner", "repo"))


@pytest.fixture
def repo_detail():
    return {
        "id": 1,
        "full_name": "owner/repo",
        "namespace": {"path": "owner"},
        "name": "repo",
        "path": "repo",
        "description": "A repo",
        "private": False,
        "internal": False,
        "fork": False,
        "default_branch": "main",
        "homepage": "https://example.com",
        "stargazers_count": 5,
        "forks_count": 2,
        "open_issues_count": 3,
        "license": "MIT",
        "owner": {"login": "owner", "name": "Owner"},
        "web_url": "https://gitcode.com/owner/repo",
        "html_url": "https://gitcode.com/owner/repo",
        "readme_url": "https://gitcode.com/owner/repo/blob/main/README.md",
        "created_at": "2026-01-01T00:00:00+08:00",
        "updated_at": "2026-02-01T00:00:00+08:00",
        "pushed_at": "2026-03-01T00:00:00+08:00",
    }


def _contents_result(text: str) -> dict:
    return {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class TestRepoView:
    def test_default_prints_metadata_and_readme(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.side_effect = [repo_detail, _contents_result("# Title\n\nreadme body")]

        result = runner.invoke(main, ["repo", "view"])

        assert result.exit_code == 0
        assert "owner/repo" in result.output
        assert "A repo" in result.output
        assert "Visibility:\tpublic" in result.output
        assert "Default Branch:\tmain" in result.output
        assert "Homepage:\thttps://example.com" in result.output
        assert "License:\tMIT" in result.output
        assert "Stars:\t5" in result.output
        assert "Forks:\t2" in result.output
        assert "Open Issues:\t3" in result.output
        assert "README:" in result.output
        assert "# Title" in result.output
        assert [c.args[0] for c in mock_client.get.call_args_list] == [
            "/repos/owner/repo",
            "/repos/owner/repo/contents/README.md",
        ]

    def test_view_omits_readme_when_missing(self, runner, mock_client, mock_repo, repo_detail):
        repo_detail.pop("readme_url")
        mock_client.get.side_effect = [repo_detail, APIError("Not Found", 404)]

        result = runner.invoke(main, ["repo", "view"])

        assert result.exit_code == 0
        assert "Visibility:\tpublic" in result.output
        assert "README:" not in result.output

    def test_view_positional_overrides_repo_flag(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["-R", "owner/other", "repo", "view", "owner/repo"])

        assert result.exit_code == 0
        assert mock_client.get.call_args_list[0].args[0] == "/repos/owner/repo"

    def test_view_url_positional(self, runner, mock_client, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["repo", "view", "https://gitcode.com/owner/repo"])

        assert result.exit_code == 0
        assert mock_client.get.call_args_list[0].args[0] == "/repos/owner/repo"

    def test_view_rejects_non_gitcode_host(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "view", "github.com/owner/repo"])
        assert result.exit_code != 0
        assert "not supported" in result.output
        mock_client.get.assert_not_called()

    def test_view_rejects_invalid_repository_format(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "view", "not-a-repo"])
        assert result.exit_code != 0
        assert "Invalid repository format" in result.output
        mock_client.get.assert_not_called()

    def test_view_web_opens_browser_without_fetching(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.repo.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["repo", "view", "-w"])
        assert result.exit_code == 0
        mock_client.get.assert_not_called()
        mock_browser.assert_called_once_with("https://gitcode.com/owner/repo")

    def test_view_web_uses_positional_repository(self, runner, mock_client, mock_repo):
        with patch("gitcode_cli.commands.repo.open_in_browser") as mock_browser:
            result = runner.invoke(main, ["repo", "view", "other/repo", "--web"])
        assert result.exit_code == 0
        mock_browser.assert_called_once_with("https://gitcode.com/other/repo")

    def test_view_json_normalizes_gh_style_fields(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(
            main, ["repo", "view", "--json", "name,nameWithOwner,isPrivate,visibility,defaultBranch,stargazers"]
        )

        assert result.exit_code == 0
        assert '"name": "repo"' in result.output
        assert '"nameWithOwner": "owner/repo"' in result.output
        assert '"isPrivate": false' in result.output
        assert '"visibility": "PUBLIC"' in result.output
        assert '"defaultBranch": "main"' in result.output
        assert '"stargazers": 5' in result.output

    def test_view_json_owner_and_url_fields(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["repo", "view", "--json", "owner,url,isFork,isArchived,pushedAt"])

        assert result.exit_code == 0
        assert '"login": "owner"' in result.output
        assert '"url": "https://gitcode.com/owner/repo"' in result.output
        assert '"isFork": false' in result.output
        assert '"isArchived": false' in result.output
        assert '"pushedAt"' in result.output

    def test_view_json_marks_archived_status(self, runner, mock_client, mock_repo, repo_detail):
        repo_detail["status"] = "已归档"
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["repo", "view", "--json", "isArchived"])

        assert result.exit_code == 0
        assert '"isArchived": true' in result.output

    def test_view_bare_json_lists_available_fields(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "view", "--json"])
        assert result.exit_code == 1
        assert "Available fields: id, name, nameWithOwner" in result.output
        mock_client.get.assert_not_called()

    def test_view_jq(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["repo", "view", "-q", ".nameWithOwner"])

        assert result.exit_code == 0
        assert result.output.strip() == '"owner/repo"'

    def test_view_template(self, runner, mock_client, mock_repo, repo_detail):
        mock_client.get.return_value = repo_detail

        result = runner.invoke(main, ["repo", "view", "-t", "{{.name}}"])

        assert result.exit_code == 0
        assert "repo" in result.output


class TestRepoList:
    def test_defaults_to_authenticated_user(self, runner, mock_client):
        mock_client.get.return_value = [{"full_name": "me/repo", "description": "d", "private": False}]

        result = runner.invoke(main, ["repo", "list"])

        assert result.exit_code == 0
        assert "me/repo\tpublic\td" in result.output
        first_call = mock_client.get.call_args_list[0]
        assert first_call.args[0] == "/user/repos"
        assert first_call.kwargs["params"] == {"page": 1, "per_page": 30}
        assert "private-token" in first_call.kwargs["headers"]

    def test_owner_argument_uses_users_endpoint(self, runner, mock_client):
        mock_client.get.return_value = [{"full_name": "owner/repo", "private": True}]

        result = runner.invoke(main, ["repo", "list", "owner"])

        assert result.exit_code == 0
        assert "owner/repo\tprivate" in result.output
        assert mock_client.get.call_args_list[0].args[0] == "/users/owner/repos"

    def test_owner_argument_falls_back_to_orgs_endpoint(self, runner, mock_client):
        mock_client.get.side_effect = [APIError("Not Found", 404), [{"full_name": "org/repo"}]]

        result = runner.invoke(main, ["repo", "list", "org"])

        assert result.exit_code == 0
        assert [c.args[0] for c in mock_client.get.call_args_list] == ["/users/org/repos", "/orgs/org/repos"]

    def test_paginates_until_limit_met(self, runner, mock_client):
        mock_client.get.side_effect = [
            [{"full_name": f"me/r-{index}"} for index in range(1, 101)],
            [{"full_name": f"me/r-{index}"} for index in range(101, 151)],
        ]

        result = runner.invoke(main, ["repo", "list", "-L", "150"])

        assert result.exit_code == 0
        assert mock_client.get.call_count == 2
        assert "me/r-1\t" in result.output
        assert "me/r-150" in result.output
        assert "me/r-151" not in result.output

    def test_json_fields(self, runner, mock_client):
        mock_client.get.return_value = [{"full_name": "me/repo", "name": "repo", "private": True, "fork": False}]

        result = runner.invoke(main, ["repo", "list", "--json", "name,nameWithOwner,isPrivate,visibility"])

        assert result.exit_code == 0
        assert '"name": "repo"' in result.output
        assert '"nameWithOwner": "me/repo"' in result.output
        assert '"isPrivate": true' in result.output
        assert '"visibility": "PRIVATE"' in result.output

    def test_bare_json_lists_available_fields(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "list", "--json"])
        assert result.exit_code == 1
        assert "Available fields: id, name, nameWithOwner" in result.output
        mock_client.get.assert_not_called()

    def test_template_renders_each_item(self, runner, mock_client):
        mock_client.get.return_value = [{"full_name": "me/a", "name": "a"}, {"full_name": "me/b", "name": "b"}]

        result = runner.invoke(main, ["repo", "list", "-t", "{{.name}}\n"])

        assert result.exit_code == 0
        assert result.output.split() == ["a", "b"]

    def test_client_side_filters(self, runner, mock_client):
        mock_client.get.return_value = [
            {"full_name": "me/source", "fork": False, "private": False, "language": "Python"},
            {"full_name": "me/forked", "fork": True, "private": True, "language": "Go"},
        ]

        result = runner.invoke(main, ["repo", "list", "--fork"])

        assert result.exit_code == 0
        assert "me/forked" in result.output
        assert "me/source" not in result.output

        result = runner.invoke(main, ["repo", "list", "--source", "--visibility", "public"])
        assert result.exit_code == 0
        assert "me/source" in result.output
        assert "me/forked" not in result.output

        result = runner.invoke(main, ["repo", "list", "-l", "go"])
        assert result.exit_code == 0
        assert "me/forked" in result.output
        assert "me/source" not in result.output

    def test_rejects_conflicting_fork_filters(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "list", "--fork", "--source"])
        assert result.exit_code != 0
        assert "specify only one of --fork or --source" in result.output
        mock_client.get.assert_not_called()

    def test_rejects_owner_repo_argument(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "list", "owner/repo"])
        assert result.exit_code != 0
        assert "owner must be a username or organization" in result.output
        mock_client.get.assert_not_called()

    def test_rejects_zero_limit(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output
        mock_client.get.assert_not_called()

    def test_empty_list_prints_nothing(self, runner, mock_client):
        mock_client.get.return_value = []
        result = runner.invoke(main, ["repo", "list"])
        assert result.exit_code == 0
        assert result.output == ""


class TestRepoCreate:
    def test_defaults_to_private_personal_repo(self, runner, mock_client):
        mock_client.post.return_value = {
            "full_name": "me/repo",
            "web_url": "https://gitcode.com/me/repo",
        }

        result = runner.invoke(main, ["repo", "create", "repo", "-d", "desc"])

        assert result.exit_code == 0
        assert "https://gitcode.com/me/repo" in result.output
        assert mock_client.post.call_args.kwargs["json"] == {"name": "repo", "description": "desc", "private": True}

    def test_public_flag(self, runner, mock_client):
        mock_client.post.return_value = {"full_name": "me/repo", "web_url": "https://gitcode.com/me/repo"}

        result = runner.invoke(main, ["repo", "create", "repo", "--public"])

        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["private"] is False

    def test_org_repo_uses_orgs_endpoint(self, runner, mock_client):
        mock_client.post.return_value = {"full_name": "org/repo", "web_url": "https://gitcode.com/org/repo"}

        result = runner.invoke(main, ["repo", "create", "org/repo", "--public"])

        assert result.exit_code == 0
        assert mock_client.post.call_args_list[0].args[0] == "/orgs/org/repos"

    def test_all_option_flags_map_to_payload(self, runner, mock_client):
        mock_client.post.return_value = {"namespace": {"path": "me"}, "name": "repo"}

        result = runner.invoke(
            main,
            [
                "repo",
                "create",
                "repo",
                "--public",
                "--add-readme",
                "--homepage",
                "https://example.com",
                "--disable-issues",
                "--disable-wiki",
                "-g",
                "Python",
                "-l",
                "mit",
            ],
        )

        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"] == {
            "name": "repo",
            "private": False,
            "auto_init": True,
            "homepage": "https://example.com",
            "has_issues": False,
            "has_wiki": False,
            "gitignore_template": "Python",
            "license_template": "mit",
        }

    def test_internal_is_unsupported(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "create", "repo", "--internal"])
        assert result.exit_code != 0
        assert "GitCode repositories are either public or private" in result.output
        mock_client.post.assert_not_called()

    def test_public_and_private_are_mutually_exclusive(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "create", "repo", "--public", "--private"])
        assert result.exit_code != 0
        assert "specify only one of --public or --private" in result.output
        mock_client.post.assert_not_called()

    def test_prompts_for_missing_name(self, runner, mock_client):
        mock_client.post.return_value = {"namespace": {"path": "me"}, "name": "prompted", "web_url": "u"}

        result = runner.invoke(main, ["repo", "create"], input="prompted\n")

        assert result.exit_code == 0
        assert mock_client.post.call_args.kwargs["json"]["name"] == "prompted"

    def test_clone_runs_git_clone(self, runner, mock_client):
        mock_client.post.return_value = {
            "full_name": "me/repo",
            "web_url": "https://gitcode.com/me/repo",
            "http_url_to_repo": "https://gitcode.com/me/repo.git",
        }

        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(main, ["repo", "create", "repo", "-c"])

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/me/repo.git"])


class TestRepoClone:
    def test_clones_gitcode_url(self, runner, mock_client):
        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(main, ["repo", "clone", "owner/repo"])

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/owner/repo.git"])

    def test_accepts_url_and_directory_and_gitflags(self, runner, mock_client):
        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(
                main, ["repo", "clone", "https://gitcode.com/owner/repo.git", "dir", "--", "--depth", "1"]
            )

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/owner/repo.git", "dir", "--depth", "1"])

    def test_gitflag_without_separator_still_passed_through(self, runner, mock_client):
        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(main, ["repo", "clone", "owner/repo", "--depth", "1"])

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/owner/repo.git", "--depth", "1"])

    def test_preserves_git_exit_code(self, runner, mock_client):
        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=128) as mock_call:
            result = runner.invoke(main, ["repo", "clone", "owner/repo"])

        assert result.exit_code == 128
        mock_call.assert_called_once()

    def test_rejects_non_gitcode_host(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "clone", "github.com/owner/repo"])
        assert result.exit_code != 0
        assert "not supported" in result.output

    def test_accepts_ssh_style_repo(self, runner, mock_client):
        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(main, ["repo", "clone", "gitcode.com:owner/repo.git"])

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/owner/repo.git"])


class TestRepoFork:
    def test_forks_origin_repo(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {"full_name": "me/repo", "web_url": "https://gitcode.com/me/repo"}

        result = runner.invoke(main, ["repo", "fork"])

        assert result.exit_code == 0
        assert "✓ Created fork me/repo" in result.output
        fork_call = mock_client.post.call_args_list[0]
        assert fork_call.args[0] == "/repos/owner/repo/forks"
        assert fork_call.kwargs["json"] is None

    def test_fork_positional_and_org(self, runner, mock_client):
        mock_client.post.return_value = {"namespace": {"path": "my-org"}, "path": "repo", "name": "repo"}

        result = runner.invoke(main, ["repo", "fork", "owner/repo", "--org", "my-org"])

        assert result.exit_code == 0
        assert "✓ Created fork my-org/repo" in result.output
        assert mock_client.post.call_args.kwargs["json"] == {"org": "my-org"}

    def test_fork_name_is_unsupported(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "fork", "owner/repo", "--fork-name", "new-name"])
        assert result.exit_code != 0
        assert "GitCode fork API does not support renaming the fork" in result.output
        mock_client.post.assert_not_called()

    def test_default_branch_only_is_unsupported(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "fork", "owner/repo", "--default-branch-only"])
        assert result.exit_code != 0
        assert "--default-branch-only is not supported" in result.output
        mock_client.post.assert_not_called()

    def test_fork_clone_runs_git_clone(self, runner, mock_client, mock_repo):
        mock_client.post.return_value = {
            "full_name": "me/repo",
            "http_url_to_repo": "https://gitcode.com/me/repo.git",
        }

        with patch("gitcode_cli.commands.repo.subprocess.call", return_value=0) as mock_call:
            result = runner.invoke(main, ["repo", "fork", "--clone"])

        assert result.exit_code == 0
        mock_call.assert_called_once_with(["git", "clone", "https://gitcode.com/me/repo.git"])


class TestRepoEdit:
    def test_edits_description(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "edit", "-d", "new desc"])

        assert result.exit_code == 0
        assert "Edited repository owner/repo" in result.output
        assert mock_client.patch.call_args.kwargs["json"] == {"description": "new desc"}

    def test_edits_all_supported_fields(self, runner, mock_client, mock_repo):
        result = runner.invoke(
            main,
            [
                "repo",
                "edit",
                "other/repo",
                "--homepage",
                "https://example.com",
                "--default-branch",
                "trunk",
                "--visibility",
                "private",
                "--disable-issues",
                "--enable-wiki",
            ],
        )

        assert result.exit_code == 0
        assert mock_client.patch.call_args_list[0].args[0] == "/repos/other/repo"
        assert mock_client.patch.call_args.kwargs["json"] == {
            "homepage": "https://example.com",
            "default_branch": "trunk",
            "private": True,
            "has_issues": False,
            "has_wiki": True,
        }

    def test_requires_at_least_one_field(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "edit"])

        assert result.exit_code != 0
        assert "must specify at least one field to edit" in result.output
        mock_client.patch.assert_not_called()


class TestRepoRename:
    def test_rename_requires_confirmation_by_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "rename", "new-name"], input="n\n")

        assert result.exit_code != 0
        assert "Rename owner/repo to new-name?" in result.output
        assert "Aborted." in result.output
        mock_client.patch.assert_not_called()

    def test_rename_yes_patches_name_and_path(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "rename", "new-name", "-y"])

        assert result.exit_code == 0
        assert "✓ Renamed repository owner/new-name" in result.output
        assert mock_client.patch.call_args.kwargs["json"] == {"name": "new-name", "path": "new-name"}

    def test_rename_prompts_for_missing_name(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "rename", "--yes"], input="prompted-name\n")

        assert result.exit_code == 0
        assert mock_client.patch.call_args.kwargs["json"]["name"] == "prompted-name"

    def test_rename_updates_matching_origin_remote(self, runner, mock_client, mock_repo):
        run_results = [
            MagicMock(stdout="https://gitcode.com/owner/repo.git\n", returncode=0),
            MagicMock(returncode=0),
        ]

        with patch("gitcode_cli.commands.repo.subprocess.run", side_effect=run_results) as mock_run:
            result = runner.invoke(main, ["repo", "rename", "new-name", "-y"])

        assert result.exit_code == 0
        assert "Updated the 'origin' remote URL to https://gitcode.com/owner/new-name.git" in result.output
        assert mock_run.call_args_list[1].args[0] == [
            "git",
            "remote",
            "set-url",
            "origin",
            "https://gitcode.com/owner/new-name.git",
        ]

    def test_rename_leaves_mismatched_origin_untouched(self, runner, mock_client, mock_repo):
        with patch(
            "gitcode_cli.commands.repo.subprocess.run",
            return_value=MagicMock(stdout="https://gitcode.com/other/repo.git\n", returncode=0),
        ) as mock_run:
            result = runner.invoke(main, ["repo", "rename", "new-name", "-y"])

        assert result.exit_code == 0
        assert "Updated the 'origin'" not in result.output
        assert mock_run.call_count == 1

    def test_rename_survives_origin_lookup_failure(self, runner, mock_client, mock_repo):
        import subprocess as real_subprocess

        with patch(
            "gitcode_cli.commands.repo.subprocess.run",
            side_effect=real_subprocess.CalledProcessError(1, "git"),
        ):
            result = runner.invoke(main, ["repo", "rename", "new-name", "-y"])

        assert result.exit_code == 0
        assert "✓ Renamed repository owner/new-name" in result.output


class TestRepoDelete:
    def test_delete_requires_confirmation_by_default(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "delete"], input="n\n")

        assert result.exit_code != 0
        assert "Delete repository owner/repo?" in result.output
        assert "Aborted." in result.output
        mock_client.delete.assert_not_called()

    def test_delete_yes_skips_confirmation(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "delete", "--yes"])

        assert result.exit_code == 0
        assert "Deleted repository owner/repo" in result.output
        delete_call = mock_client.delete.call_args_list[0]
        assert delete_call.args[0] == "/repos/owner/repo"

    def test_delete_positional_repository(self, runner, mock_client, mock_repo):
        result = runner.invoke(main, ["repo", "delete", "other/repo", "--yes"])

        assert result.exit_code == 0
        assert "Deleted repository other/repo" in result.output


class TestRepoSync:
    def test_sync_puts_sync_endpoint(self, runner, mock_client, mock_repo):
        mock_client.put.return_value = {"repo_sync_result": True}

        result = runner.invoke(main, ["repo", "sync"])

        assert result.exit_code == 0
        assert '✓ Synced the "owner/repo" repository from its upstream source' in result.output
        sync_call = mock_client.put.call_args_list[0]
        assert sync_call.args[0] == "/repos/owner/repo/sync_repo"

    def test_sync_positional_repository(self, runner, mock_client):
        result = runner.invoke(main, ["repo", "sync", "other/repo"])

        assert result.exit_code == 0
        assert mock_client.put.call_args_list[0].args[0] == "/repos/other/repo/sync_repo"


class TestRepoHelpSections:
    def test_group_lists_subcommands(self, runner):
        result = runner.invoke(main, ["repo", "--help"])
        assert result.exit_code == 0
        for name in ("view", "list", "create", "clone", "fork", "edit", "rename", "delete", "sync"):
            assert name in result.output

    def test_view_help_lists_json_fields(self, runner):
        result = runner.invoke(main, ["repo", "view", "--help"])
        assert result.exit_code == 0
        assert "JSON FIELDS" in result.output
        assert "nameWithOwner" in result.output

    def test_list_help_lists_json_fields(self, runner):
        result = runner.invoke(main, ["repo", "list", "--help"])
        assert result.exit_code == 0
        assert "JSON FIELDS" in result.output
        assert "isArchived" not in result.output.split("EXAMPLES")[0]

    def test_create_help_documents_private_default(self, runner):
        result = runner.invoke(main, ["repo", "create", "--help"])
        assert result.exit_code == 0
        assert "private (the default)" in result.output
        assert "Unsupported: GitCode has no internal repositories" in result.output
