"""Local Git default selection and its routing boundaries, with real Git repositories."""

from __future__ import annotations

import os
import subprocess

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.commands import issue, pr, repo
from gitcode_cli.context import AppContext
from gitcode_cli.errors import RepoResolutionError
from gitcode_cli.gh_proxy import ProxyError, dispatch, select_target
from gitcode_cli.repo import resolve_repo
from gitcode_cli.repo_default import configured_target
from gitcode_cli.repo_read_dir import TreeEntry

KEY = "gc.default-repository"


def git(*args: str, check: bool = True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


@pytest.fixture
def checkout(monkeypatch, tmp_path, tmp_config_dir, mock_app_context):
    for name in os.environ:
        if name.startswith("GIT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GC_GH_PROXY_ACTIVE", raising=False)
    monkeypatch.setenv("GC_TOKEN", "unused-synthetic-token")
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.chdir(root)
    git("init", "-q")
    git("remote", "add", "origin", "https://gitcode.com/my-fork/repo.git")
    git("remote", "add", "upstream", "ssh://git@ssh.gitcode.com:443/Project/Repo.Name.git/")
    return root


def cli(*args: str):
    return CliRunner().invoke(main, list(args))


@pytest.mark.usefixtures("checkout")
def test_set_view_and_unset_in_local_config(monkeypatch):
    monkeypatch.setattr(AppContext, "client", lambda _: pytest.fail("set-default must not create an HTTP client"))
    assert resolve_repo() == ("my-fork", "repo")

    assert cli("repo", "set-default", "upstream").exit_code == 0
    assert git("config", "--local", "--get", KEY).stdout == "upstream\tProject/Repo.Name\n"
    assert cli("repo", "set-default", "-v").output == "Project/Repo.Name\n"
    assert configured_target() == ("Project", "Repo.Name")
    assert resolve_repo("gitcode.com/another/project") == ("another", "project")

    opened = []
    monkeypatch.setattr("gitcode_cli.commands.repo.open_in_browser", opened.append)
    assert cli("repo", "view", "--web").exit_code == 0
    assert cli("-R", "separate/explicit", "repo", "view", "--web").exit_code == 0
    assert cli("repo", "view", "-R", "other/repo", "--web").exit_code == 0
    assert opened == [
        "https://gitcode.com/Project/Repo.Name",
        "https://gitcode.com/separate/explicit",
        "https://gitcode.com/other/repo",
    ]
    assert cli("repo", "set-default", "-u").exit_code == 0
    assert cli("repo", "set-default", "--unset").exit_code == 0
    assert "No GitCode read default is set" in cli("repo", "set-default", "--view").output
    assert git("config", "--local", "--get", KEY, check=False).returncode == 1
    assert resolve_repo() == ("my-fork", "repo")


@pytest.mark.usefixtures("checkout")
def test_default_does_not_apply_to_issue_writes_or_repository_management(monkeypatch, mock_issue_data):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    targets = []

    def create(adapter, owner, name, *args, **kwargs):
        targets.append(("issue create", owner, name))
        return mock_issue_data

    def delete(service, owner, name):
        targets.append(("repo delete", owner, name))

    monkeypatch.setattr(issue.IssueAdapter, "create_issue", create)
    monkeypatch.setattr(repo.RepoService, "delete", delete)
    assert cli("issue", "create", "--title", "test", "--body", "fixture").exit_code == 0
    assert cli("issue", "create", "-R", "override/project", "--title", "test", "--body", "fixture").exit_code == 0
    assert cli("repo", "delete", "--yes").exit_code == 0
    assert targets == [
        ("issue create", "my-fork", "repo"),
        ("issue create", "override", "project"),
        ("repo delete", "my-fork", "repo"),
    ]


@pytest.mark.usefixtures("checkout")
def test_configuration_is_local_and_shared_with_linked_worktrees(monkeypatch, tmp_path):
    git("config", "--global", KEY, "upstream\tProject/Repo.Name")
    assert configured_target() is None
    assert resolve_repo() == ("my-fork", "repo")
    assert cli("repo", "set-default", "gitcode.com/Project/Repo.Name").exit_code == 0
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "fixture")
    worktree = tmp_path / "linked"
    git("config", "--local", "extensions.worktreeConfig", "true")
    git("worktree", "add", "--detach", str(worktree), "HEAD")
    monkeypatch.chdir(worktree)
    git("config", "--worktree", KEY, "origin\tmy-fork/repo")
    assert configured_target() == ("Project", "Repo.Name")
    assert cli("repo", "set-default", "--unset").exit_code == 0
    assert resolve_repo() == ("my-fork", "repo")
    assert configured_target() is None
    assert git("config", "--global", "--get", KEY).stdout == "upstream\tProject/Repo.Name\n"
    assert git("config", "--worktree", "--get", KEY).stdout == "origin\tmy-fork/repo\n"


@pytest.mark.usefixtures("checkout")
@pytest.mark.parametrize("change", ["remove", "repoint", "foreign", "rewrite", "duplicates", "broken-setting"])
def test_stale_or_ambiguous_target_fails_closed(change, monkeypatch):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    if change == "remove":
        git("remote", "remove", "upstream")
    elif change == "repoint":
        git("remote", "set-url", "upstream", "https://gitcode.com/other/repo")
    elif change == "foreign":
        git("remote", "set-url", "upstream", "https://github.com/Project/Repo.Name")
    elif change == "rewrite":
        git("config", "url.https://github.com/.insteadOf", "ssh://git@ssh.gitcode.com:443/")
    elif change == "duplicates":
        git("config", "--add", KEY, "origin\tmy-fork/repo")
    else:
        git("config", KEY, "--an-invalid-value")
    with pytest.raises(RepoResolutionError, match="configured GitCode default"):
        configured_target()
    assert cli("repo", "set-default", "--view").exit_code == 1
    monkeypatch.setattr(AppContext, "client", lambda _: pytest.fail("stale default must not reach API selection"))
    result = cli("repo", "view")
    assert result.exit_code == 1
    assert "configured GitCode default" in result.output
    assert resolve_repo() == ("my-fork", "repo")  # even a stale read pin cannot redirect or break writes
    assert resolve_repo("other/explicit") == ("other", "explicit")
    assert cli("repo", "set-default", "--unset").exit_code == 0
    assert resolve_repo() == ("my-fork", "repo")


@pytest.mark.usefixtures("checkout")
def test_fetch_identity_excludes_foreign_owner_repo_collision_and_push_urls():
    git("remote", "set-url", "origin", "https://github.com/Project/Repo.Name.git")
    git("remote", "set-url", "--push", "upstream", "https://github.com/other/not-the-fetch-repo.git")
    assert cli("repo", "set-default", "Project/Repo.Name").exit_code == 0
    assert git("config", "--local", "--get", KEY).stdout == "upstream\tProject/Repo.Name\n"
    assert configured_target() == ("Project", "Repo.Name")
    assert cli("repo", "set-default", "origin").exit_code == 1
    assert cli("repo", "set-default", "github.com/Project/Repo.Name").exit_code == 1
    git("remote", "add", "mirror", "https://gitcode.com/Project/Repo.Name.git")
    assert cli("repo", "set-default", "Project/Repo.Name").exit_code == 1
    assert cli("repo", "set-default", "mirror").exit_code == 0
    git("remote", "set-url", "--add", "mirror", "https://gitcode.com/Project/Other.git")
    with pytest.raises(RepoResolutionError, match="configured GitCode default"):
        configured_target()


@pytest.mark.usefixtures("checkout")
@pytest.mark.parametrize(
    "url",
    (
        "https://secret-userinfo:secret-password@gitcode.com/Project/Repo.git",
        "https://gitcode.com:8000/Project/Repo.git",
        "https://gitcode.com/Project/Repo.git?secret-query=secret-value",
        "gitcode::https://gitcode.com/Project/Repo",
        "https://gitcode.com/Project/Repo%2fName",
    ),
)
def test_ineligible_urls_never_appear_in_output_or_set_config(monkeypatch, tmp_path, url):
    git("remote", "set-url", "upstream", url)
    trace = tmp_path / "trace"
    monkeypatch.setenv("GIT_TRACE", str(trace))
    monkeypatch.setattr(AppContext, "client", lambda _: pytest.fail("set-default must not create an HTTP client"))
    result = cli("repo", "set-default", "upstream")
    assert result.exit_code == 1
    assert url not in result.output
    assert "secret" not in result.output
    assert not trace.exists()
    monkeypatch.delenv("GIT_TRACE")
    assert not git("config", "--local", "--get", KEY, check=False).stdout


@pytest.mark.usefixtures("checkout")
@pytest.mark.parametrize("args", [(), ("--unset", "--view"), ("upstream", "--view"), ("--unset", "origin")])
def test_requires_exactly_one_mode(args):
    assert cli("repo", "set-default", *args).exit_code == 2
    assert cli("-R", "other/repo", "repo", "set-default", "upstream").exit_code == 2
    assert not git("config", "--local", "--get", KEY, check=False).stdout


def test_exits_outside_git(monkeypatch, tmp_path, tmp_config_dir, mock_app_context):
    monkeypatch.chdir(tmp_path)
    for args in (("--view",), ("--unset",), ("upstream",)):
        assert cli("repo", "set-default", *args).exit_code == 1


@pytest.mark.usefixtures("checkout")
def test_default_does_not_change_proxy_routing_or_dispatch(monkeypatch):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    implicit = ["pr", "list"]
    assert select_target(implicit, {}) == "gitcode"
    monkeypatch.setenv("GC_GH_PROXY_ACTIVE", "1")
    assert configured_target() is None
    assert resolve_repo() == ("my-fork", "repo")
    monkeypatch.delenv("GC_GH_PROXY_ACTIVE")
    git("remote", "set-url", "origin", "https://github.com/Project/Repo.Name.git")
    assert configured_target() == ("Project", "Repo.Name")
    assert select_target(implicit, {}) == "github"
    assert select_target(["pr", "list", "-R", "gitcode.com/Project/Repo.Name"], {}) == "gitcode"
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/fake/gh")
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    assert dispatch(implicit, {}) == 0
    assert calls == [("/fake/gh", implicit, {})]
    for selector in ("gitcode.com/Project/Repo.Name", "HTTPS://GITCODE.COM/Project/Repo.Name", "upstream"):
        with pytest.raises(ProxyError, match="use gc repo set-default directly"):
            dispatch(["repo", "set-default", selector], {})
        with pytest.raises(ProxyError, match="conflicts with GC_GH_TARGET"):
            dispatch(["repo", "set-default", selector], {"GC_GH_TARGET": "github"})
    assert calls == [("/fake/gh", implicit, {})]


@pytest.mark.usefixtures("checkout")
def test_pinned_file_and_directory_only_use_verified_default(monkeypatch):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    seen = []
    monkeypatch.setattr(repo, "fetch_file", lambda o, n, *args: seen.append(("file", o, n)) or b"safe")
    entry = TreeEntry(name="safe", path="safe", mode="100644", kind="blob", sha="a" * 40)
    monkeypatch.setattr(repo, "fetch_page", lambda o, n, *args: seen.append(("dir", o, n)) or [entry])
    assert cli("repo", "read-file", "README").exit_code == 0
    assert cli("repo", "read-dir", "--ref", "main").exit_code == 0
    projected = cli("repo", "read-dir", "--ref", "main", "--json", "path")
    assert (projected.exit_code, projected.stdout) == (0, '[{"path": "safe"}]\n')
    git("remote", "remove", "upstream")
    assert cli("repo", "read-dir", "--ref", "main").exit_code == 1
    assert cli("repo", "read-file", "README").exit_code == 1
    assert cli("repo", "read-file", "README", "-R", "explicit/a").exit_code == 0
    assert cli("-R", "explicit/b", "repo", "read-dir", "--ref", "main").exit_code == 0
    assert seen == [
        ("file", "Project", "Repo.Name"),
        ("dir", "Project", "Repo.Name"),
        ("dir", "Project", "Repo.Name"),
        ("file", "explicit", "a"),
        ("dir", "explicit", "b"),
    ]


@pytest.mark.usefixtures("checkout")
@pytest.mark.parametrize(
    "args",
    [
        ("repo", "view", "-R", "", "--web"),
        ("-R", "", "repo", "view", "valid/repo", "--web"),
        ("repo", "view", "", "--web"),
        ("repo", "read-file", "README", "-R", ""),
        ("-R", "", "repo", "read-dir", "--ref", "main"),
    ],
)
def test_empty_explicit_selector_never_reaches_default_or_io(args, monkeypatch):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    monkeypatch.setattr(repo, "configured_target", lambda: pytest.fail("unexpected default lookup"))
    assert cli(*args).exit_code == 2


@pytest.mark.usefixtures("checkout")
def test_pin_does_not_change_branch_inference_or_target_of_pr_mutation(monkeypatch):
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "fixture")
    git("checkout", "-qb", "feature")
    assert cli("repo", "set-default", "upstream").exit_code == 0
    requests = []

    def listed(_service, owner, name, **params):
        requests.append(("list", owner, name, params["head"]))
        return [{"number": 42, "head": {"ref": "feature"}}]

    def update(_service, owner, name, number, **_params):
        requests.append(("close", owner, name, number))
        return {"state": "closed", "number": number}

    monkeypatch.setattr(pr.PullRequestService, "list", listed)
    monkeypatch.setattr(pr.PullRequestService, "update", update)
    assert cli("pr", "close").exit_code == 0
    assert requests == [("list", "my-fork", "repo", "feature"), ("close", "my-fork", "repo", 42)]


@pytest.mark.usefixtures("checkout")
@pytest.mark.parametrize(
    "case",
    ["include", "rewrite-to-gitcode", "rewrite-from-gitcode", "explicit-port", "ambiguous", "custom-host", "global"],
)
def test_gitcode_named_selector_never_reaches_either_backend(case, monkeypatch):
    git("remote", "set-url", "origin", "https://github.com/local/repo")
    hosts = {}
    if case == "include":
        git("config", "--file", ".git/peers", "remote.peer.url", "https://gitcode.com/other/repo")
        git("config", "--local", "include.path", "peers")
    elif case == "rewrite-to-gitcode":
        git("remote", "add", "peer", "gc:other/repo")
        git("config", "url.https://gitcode.com/.insteadOf", "gc:")
    elif case == "rewrite-from-gitcode":
        git("remote", "add", "peer", "https://gitcode.com/other/repo")
        git("config", "url.https://github.com/.insteadOf", "https://gitcode.com/")
    elif case == "explicit-port":
        git("remote", "add", "peer", "https://gitcode.com:443/other/repo")
    elif case == "ambiguous":
        git("remote", "add", "peer", "https://github.com/other/repo")
        git("config", "--add", "remote.peer.url", "https://gitcode.com/other/repo")
    elif case == "global":
        git("config", "--global", "remote.peer.url", "https://gitcode.com/other/repo")
    else:
        git("remote", "add", "peer", "https://enterprise.example/other/repo")
        hosts["GC_GITCODE_HOSTS"] = "enterprise.example"
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("must not dispatch"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda *_: pytest.fail("must not select native gh"))
    for env in (hosts, {**hosts, "GC_GH_TARGET": "github"}):
        with pytest.raises(ProxyError):
            dispatch(["repo", "set-default", "peer"], env)


@pytest.mark.usefixtures("checkout")
def test_explicit_native_remote_beats_gitcode_origin_with_no_pin_leak(monkeypatch):
    assert cli("repo", "set-default", "upstream").exit_code == 0
    git("remote", "add", "native", "https://github.com/owner/repo")
    forwarded = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: forwarded.append(args) or 0)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    args = ["repo", "set-default", "native"]
    assert dispatch(args, {}) == 0
    assert forwarded == [("/native/gh", args, {})]


@pytest.mark.usefixtures("checkout")
def test_extra_included_fetch_url_cannot_redirect_read_and_a_scoped_pin_is_ignored():
    git("config", "--file", ".git/included", KEY, "bad-included-pin")
    git("config", "--local", "include.path", "included")
    assert configured_target() is None
    assert cli("repo", "set-default", "upstream").exit_code == 0
    git("config", "--file", ".git/included", "remote.upstream.url", "https://github.com/Project/Repo.Name")
    with pytest.raises(RepoResolutionError, match="configured GitCode default"):
        configured_target()
