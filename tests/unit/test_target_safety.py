"""Host and source-commit binding, including real offline Git lease checks."""

import os
import subprocess
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from gitcode_cli import gh_proxy, pr_git
from gitcode_cli.cli import main
from gitcode_cli.errors import GCError

SHA = "a" * 40


@pytest.mark.parametrize(
    ("url", "matches"),
    [
        ("https://gitcode.com/fork/project.git", True),
        ("https://gitcode.com/fork/project", True),
        ("git@gitcode.com:fork/project.git", True),
        ("ssh://git@ssh.gitcode.com/fork/project.git", True),
        ("https://gitcode.com:8443/fork/project.git", False),
        ("https://synthetic-user@gitcode.com/fork/project.git", False),
        ("ssh://git@gitcode.com:2222/fork/project.git", False),
        ("https://github.com/fork/project.git", False),
        ("https://gitcode.com/other/project.git", False),
        ("ext::synthetic-helper", False),
        ("https://gitcode.com/fork/project.git\nhttps://gitcode.com/other/project.git", False),
        ("", False),
    ],
)
def test_force_upstream_requires_canonical_source_identity(monkeypatch, url, matches):
    git = MagicMock(return_value=MagicMock(stdout=url))
    monkeypatch.setattr(pr_git, "_git", git)
    source = pr_git.PRHead("https://gitcode.com/fork/project.git", "feature", SHA)
    assert pr_git._remote_matches(source, "source") is matches
    git.assert_called_once_with("remote", "get-url", "--all", "--", "source")


@pytest.fixture(autouse=True)
def synthetic_auth(monkeypatch):
    monkeypatch.setenv("GC_TOKEN", "synthetic-target-test-token")


def pr_head(sha=SHA):
    return {"head": {"ref": "feature", "sha": sha, "repo": {"full_name": "fork/project"}}}


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("source", ["global", "command", "url", "origin"])
def test_foreign_targets_fail_before_api(kind, source, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    monkeypatch.setattr(
        "gitcode_cli.repo.subprocess.run", MagicMock(return_value=MagicMock(stdout="git@github.com:owner/repo.git"))
    )
    identifier = (
        f"https://github.com/owner/repo/{'issues' if kind == 'issue' else 'pull'}/1" if source == "url" else "1"
    )
    args = [kind, "close", identifier]
    if source == "global":
        args = ["-R", "github.com/owner/repo", *args]
    elif source == "command":
        args += ["-R", "github.com/owner/repo"]
    result = cli_runner.invoke(main, args)
    assert result.exit_code == 1
    assert "host" in result.output
    assert not client.mock_calls


@pytest.mark.parametrize("kind", ["issue", "pr"])
def test_gitcode_url_works_without_origin(kind, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    client.get.return_value = {"number": 1, "title": "hello"}
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    run = MagicMock(side_effect=AssertionError("must not resolve origin"))
    monkeypatch.setattr("gitcode_cli.repo.subprocess.run", run)
    endpoint = "issues" if kind == "issue" else "pulls"
    result = cli_runner.invoke(main, [kind, "view", f"https://gitcode.com/owner/repo/{endpoint}/1", "--json", "number"])
    assert result.exit_code == 0, result.output
    client.get.assert_called_once_with(f"/repos/owner/repo/{endpoint}/1")


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("host", ["github.com", "gitcode.com"])
def test_proxy_routes_resource_url_instead_of_origin(kind, host, monkeypatch):
    monkeypatch.setattr(gh_proxy, "_origin_host", lambda: "gitcode.com" if host == "github.com" else "github.com")
    endpoint = "issues" if kind == "issue" else "pulls"
    url = f"https://{host}/owner/repo/{endpoint}/1"
    assert gh_proxy.select_target([kind, "view", "--json", "title", url], {}) == (
        "github" if host == "github.com" else "gitcode"
    )


def test_proxy_ignores_urls_in_option_values(monkeypatch):
    monkeypatch.setattr(gh_proxy, "_origin_host", lambda: "gitcode.com")
    assert gh_proxy.select_target(["pr", "comment", "--body", "https://github.com/o/r/pull/1", "2"], {}) == "gitcode"


def test_proxy_ignores_repo_flag_inside_body(monkeypatch):
    monkeypatch.setattr(gh_proxy, "_origin_host", lambda: "gitcode.com")
    assert gh_proxy.select_target(["pr", "comment", "--body", "-Rgithub.com/o/r", "2"], {}) == "gitcode"


@pytest.mark.parametrize(
    "options", [["review", "--comment"], ["review", "-c"], ["review", "-a"], ["audit", "-s", "open"]]
)
def test_proxy_respects_subcommand_specific_option_arity(options, monkeypatch):
    monkeypatch.setattr(gh_proxy, "_origin_host", lambda: "gitcode.com")
    assert gh_proxy.select_target(["pr", *options, "https://github.com/o/r/pull/1"], {}) == "github"


def test_proxy_explicit_repo_after_boolean_option(monkeypatch):
    monkeypatch.setattr(gh_proxy, "_origin_host", lambda: "gitcode.com")
    assert gh_proxy.select_target(["pr", "close", "-d", "-R", "github.com/o/r", "1"], {}) == "github"


@pytest.mark.parametrize("kind", ["pr", "issue"])
def test_conflicting_url_and_explicit_repository_never_write(kind, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    endpoint = "pulls" if kind == "pr" else "issues"
    result = cli_runner.invoke(
        main, [kind, "close", f"https://gitcode.com/owner/repo/{endpoint}/1", "-R", "other/repo"]
    )
    assert result.exit_code == 1
    assert "conflicts" in result.output
    assert not client.mock_calls


@pytest.mark.parametrize("command", ["close", "merge"])
@pytest.mark.parametrize("url", [False, True])
def test_cross_repository_command_deletes_only_verified_fork(command, url, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    client.get.return_value = pr_head()
    client.patch.return_value = {"state": "closed", "number": 1}
    client.put.return_value = {"merged": True}
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    git = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(pr_git, "_git", git)
    source_git = MagicMock()
    monkeypatch.setattr(pr_git, "_git_source", source_git)
    args = ["https://gitcode.com/base/project/pulls/1"] if url else ["1", "-R", "base/project"]
    result = cli_runner.invoke(main, ["pr", command, *args, "--delete-branch"])
    assert result.exit_code == 0, result.output
    client.get.assert_called_once_with("/repos/base/project/pulls/1")
    source_git.assert_called_once_with(
        pr_git.PRHead("https://gitcode.com/fork/project.git", "feature", SHA),
        "push",
        ":refs/heads/feature",
        f"--force-with-lease=refs/heads/feature:{SHA}",
    )


@pytest.mark.parametrize("response", [None, {}, {"state": "open"}, []])
def test_unconfirmed_close_never_deletes(response, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    client.get.return_value = pr_head()
    client.patch.return_value = response
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    git = MagicMock()
    monkeypatch.setattr(pr_git, "_git", git)
    result = cli_runner.invoke(main, ["pr", "close", "1", "-R", "base/project", "--delete-branch"])
    assert result.exit_code == 1
    assert "not confirmed" in result.output
    git.assert_not_called()


def test_source_identity_can_use_canonical_repo_url(monkeypatch):
    item = pr_head()
    item["head"]["repo"] = {"html_url": "https://gitcode.com/fork/project"}
    monkeypatch.setattr(pr_git, "_git", MagicMock(return_value=MagicMock(returncode=0)))
    assert pr_git.resolve_head(item).url == "https://gitcode.com/fork/project.git"


def test_conflicting_source_identities_fail_closed(monkeypatch):
    item = pr_head()
    item["head"]["repo"]["html_url"] = "https://gitcode.com/other/project"
    git = MagicMock()
    monkeypatch.setattr(pr_git, "_git", git)
    with pytest.raises(GCError, match="disagree"):
        pr_git.delete_head(item)
    git.assert_not_called()


def test_default_branch_is_never_deleted(monkeypatch):
    item = pr_head()
    item["head"]["repo"]["default_branch"] = "feature"
    git = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(pr_git, "_git", git)
    with pytest.raises(GCError, match="default"):
        pr_git.delete_head(item)
    assert not any(call.args[0] == "push" for call in git.call_args_list)


@pytest.mark.parametrize("suffix", ["/extra", "evil", "%2f", "?x=1/extra"])
def test_malformed_resource_path_never_becomes_a_branch(suffix, cli_runner, mock_app_context, monkeypatch):
    if suffix.startswith("?"):
        suffix = "/" + suffix
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    result = cli_runner.invoke(main, ["pr", "close", "https://github.com/o/r/pull/1" + suffix])
    assert result.exit_code == 1
    assert not client.mock_calls


def test_delete_uses_source_repository_and_explicit_sha_lease(monkeypatch):
    git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(pr_git, "_git", git)
    source_git = MagicMock()
    monkeypatch.setattr(pr_git, "_git_source", source_git)
    assert pr_git.delete_head(pr_head()) == "feature"
    source_git.assert_called_once_with(
        pr_git.PRHead("https://gitcode.com/fork/project.git", "feature", SHA),
        "push",
        ":refs/heads/feature",
        f"--force-with-lease=refs/heads/feature:{SHA}",
    )


@pytest.mark.parametrize(
    "head",
    [
        {},
        {"head": {"ref": "feature"}},
        {"head": {"ref": "feature", "sha": "abc", "repo": {"full_name": "o/r"}}},
        {"head": {"ref": "feature", "sha": SHA, "repo": {"full_name": "github.com/o/r"}}},
    ],
)
def test_unverified_head_never_reaches_git(head, monkeypatch):
    git = MagicMock()
    monkeypatch.setattr(pr_git, "_git", git)
    with pytest.raises(GCError):
        pr_git.delete_head(head)
    git.assert_not_called()


def test_checkout_rejects_source_move_before_local_switch(monkeypatch):
    git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "b" * 40, ""))
    monkeypatch.setattr(pr_git, "_git", git)
    monkeypatch.setattr(pr_git, "_git_source", MagicMock())
    with pytest.raises(GCError, match="changed during fetch"):
        pr_git.checkout_head(pr_head(), None)
    assert not any(call.args[0] == "checkout" for call in git.call_args_list)


def test_real_git_lease_keeps_concurrently_updated_branch(tmp_path, monkeypatch):
    # Git can export GIT_DIR/GIT_INDEX_FILE while running commit hooks; those
    # would redirect the synthetic repositories into the caller's checkout.
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    remote = tmp_path / "source.git"
    local = tmp_path / "local"

    def git(*args, cwd=tmp_path, check=True):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=", *map(str, args)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )

    # An empty template and disabled hooks keep the synthetic repository
    # independent of the developer's global Git configuration.
    git("init", "--template=", "--bare", remote)
    git("init", "--template=", local)
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "first",
        cwd=local,
    )
    first = git("rev-parse", "HEAD", cwd=local).stdout.strip()
    git("push", remote, "HEAD:refs/heads/feature", cwd=local)
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "second",
        cwd=local,
    )
    second = git("rev-parse", "HEAD", cwd=local).stdout.strip()
    git("push", remote, "HEAD:refs/heads/feature", cwd=local)
    monkeypatch.chdir(local)
    original = pr_git._git_source

    def mapped_git(source, *args):
        return original(replace(source, url=remote.as_uri()), *args)

    monkeypatch.setattr(pr_git, "_git_source", mapped_git)
    with pytest.raises(GCError):
        pr_git.delete_head(pr_head(first))
    assert git("rev-parse", "--verify", "refs/heads/feature", cwd=remote).stdout.strip() == second
    pr_git.delete_head(pr_head(second))
    assert git("show-ref", "--verify", "refs/heads/feature", cwd=remote, check=False).returncode != 0
