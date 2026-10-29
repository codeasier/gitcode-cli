"""Exercise PR checkout and patch output against disposable Git repositories, without API access."""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli import pr_git
from gitcode_cli.cli import main


def _git(path, *args, check=True, input_text=None):
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=path,
        capture_output=True,
        text=True,
        input=input_text,
        check=check,
    )


@pytest.fixture
def checkout_repo(tmp_path, monkeypatch, tmp_config_dir):
    monkeypatch.delenv("GC_TOKEN", raising=False)
    # A parent `git commit` exports GIT_INDEX_FILE into pre-commit's pytest hook.
    # Keep all Git operations, configuration, and indexes inside the disposable repos.
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    template = tmp_path / "empty-template"
    template.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(template))
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    (seed / "file.txt").write_text("base\n")
    _git(seed, "add", "file.txt")
    _git(seed, "commit", "-m", "Base")
    _git(seed, "checkout", "-b", "feature")
    (seed / "file.txt").write_text("first\n")
    _git(seed, "commit", "-am", "First PR commit")
    initial_sha = _git(seed, "rev-parse", "HEAD").stdout.strip()
    _git(tmp_path, "clone", "--bare", str(seed), str(tmp_path / "origin.git"))
    _git(tmp_path, "clone", str(tmp_path / "origin.git"), str(tmp_path / "work"))
    work = tmp_path / "work"
    source_url = (tmp_path / "origin.git").as_uri()
    _git(work, "remote", "set-url", "origin", source_url)
    _git(work, "checkout", "main")
    (seed / "file.txt").write_text("latest\n")
    _git(seed, "commit", "-am", "Latest PR commit")
    latest_sha = _git(seed, "rev-parse", "HEAD").stdout.strip()
    _git(seed, "push", str(tmp_path / "origin.git"), "feature")
    client = MagicMock()
    client.get.return_value = {"head": {"ref": "feature", "sha": latest_sha, "repo": {"full_name": "fork/project"}}}
    resolve = pr_git.resolve_head

    def offline_source(item):
        # Keep production metadata validation; substitute only the synthetic
        # transport endpoint. All fetch, rewrite, SHA and checkout work is real.
        return replace(resolve(item), url=source_url)

    monkeypatch.setattr(pr_git, "resolve_head", offline_source)
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
    monkeypatch.chdir(work)
    return work, initial_sha, latest_sha, client


def test_detach_uses_fetched_head_and_leaves_local_branches_unchanged(checkout_repo):
    work, initial_sha, latest_sha, _ = checkout_repo
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", "--detach"])

    assert result.exit_code == 0, result.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == latest_sha
    assert _git(work, "symbolic-ref", "-q", "HEAD", check=False).returncode == 1
    assert _git(work, "rev-parse", "feature").stdout.strip() == initial_sha
    assert (work / "file.txt").read_text() == "latest\n"


@pytest.mark.parametrize("custom_branch", [None, "local-review"])
def test_force_resets_existing_tracking_branch_to_fetched_head(checkout_repo, custom_branch):
    work, _, latest_sha, _ = checkout_repo
    branch = custom_branch or "feature"
    if custom_branch:
        _git(work, "checkout", "-b", branch, "--track", "origin/feature")
    else:
        _git(work, "checkout", branch)
    (work / "file.txt").write_text("local commit\n")
    _git(work, "commit", "-am", "Local divergence")
    (work / "file.txt").write_text("uncommitted change\n")
    args = ["pr", "checkout", "42", "-R", "owner/repo", "--force"]
    if custom_branch:
        args.extend(["--branch", custom_branch])
    result = CliRunner().invoke(main, args)

    assert result.exit_code == 0, result.output
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == branch
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == latest_sha
    assert (work / "file.txt").read_text() == "latest\n"
    assert _git(work, "status", "--porcelain").stdout == ""


def test_force_creates_new_branch_from_latest_remote_head(checkout_repo):
    work, _, latest_sha, _ = checkout_repo
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", "--force", "--branch", "new-review"])

    assert result.exit_code == 0, result.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == latest_sha
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == "new-review"


def test_force_uses_verified_source_not_a_hardcoded_remote_name(checkout_repo):
    work, _, latest_sha, _ = checkout_repo
    _git(work, "remote", "rename", "origin", "source-fork")
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", "--force"])

    assert result.exit_code == 0, result.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == latest_sha


@pytest.mark.parametrize("new_source_branch", [False, True])
def test_new_checkout_preserves_verified_upstream_for_later_force(checkout_repo, new_source_branch):
    work, _, _, client = checkout_repo
    seed = work.parent / "seed"
    source_branch = "new-source" if new_source_branch else "feature"
    if new_source_branch:
        # This branch was created after clone, so no local tracking ref exists.
        _git(seed, "push", str(work.parent / "origin.git"), f"HEAD:{source_branch}")
        client.get.return_value["head"]["ref"] = source_branch
    args = ["pr", "checkout", "42", "-R", "owner/repo", "--branch", "new-review"]
    first = CliRunner().invoke(main, args)
    assert first.exit_code == 0, first.output
    assert _git(work, "rev-parse", "--abbrev-ref", "new-review@{upstream}").stdout.strip() == f"origin/{source_branch}"
    (seed / "file.txt").write_text("new push\n")
    _git(seed, "commit", "-am", "Subsequent PR push")
    _git(seed, "push", str(work.parent / "origin.git"), f"HEAD:{source_branch}")
    expected = _git(seed, "rev-parse", "HEAD").stdout.strip()
    client.get.return_value["head"]["sha"] = expected

    second = CliRunner().invoke(main, [*args, "--force"])
    assert second.exit_code == 0, second.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == expected
    assert (work / "file.txt").read_text() == "new push\n"


@pytest.mark.parametrize("upstream", ["none", "other-ref", "other-repo"])
def test_force_refuses_unverified_tracking_without_resetting_branch(checkout_repo, upstream):
    work, initial_sha, _, _ = checkout_repo
    if upstream == "none":
        _git(work, "branch", "--unset-upstream", "feature")
    elif upstream == "other-ref":
        _git(work, "branch", "--set-upstream-to=origin/main", "feature")
    else:
        # The second repository advertises the SAME commit; SHA equality cannot
        # establish which repository the user's branch tracks.
        other = work.parent / "other.git"
        _git(work.parent, "clone", "--bare", str(work.parent / "origin.git"), str(other))
        _git(work, "remote", "set-url", "origin", other.as_uri())
    original_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", "--force"])

    assert result.exit_code == 1
    assert "does not track the verified PR source" in result.output
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == original_head
    assert _git(work, "rev-parse", "feature").stdout.strip() == initial_sha


def test_new_checkout_never_overwrites_concurrently_created_tracking_ref(checkout_repo, monkeypatch):
    work, initial_sha, _, _ = checkout_repo
    tracking_ref = "refs/remotes/origin/feature"
    _git(work, "update-ref", "-d", tracking_ref)
    original = pr_git._git

    def race_after_missing_ref(*args, **kwargs):
        result = original(*args, **kwargs)
        if args == ("show-ref", "--verify", "--quiet", tracking_ref):
            assert result.returncode != 0
            _git(work, "update-ref", tracking_ref, initial_sha)
        return result

    monkeypatch.setattr(pr_git, "_git", race_after_missing_ref)
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", "--branch", "new-review"])

    assert result.exit_code == 1
    assert "Git operation failed" in result.output
    assert _git(work, "rev-parse", tracking_ref).stdout.strip() == initial_sha
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert _git(work, "show-ref", "--verify", "refs/heads/new-review", check=False).returncode != 0


@pytest.mark.parametrize("flag", ["--force", "--detach"])
def test_checkout_refuses_head_mismatch_before_changing_checkout(checkout_repo, flag):
    work, initial_sha, _, client = checkout_repo
    original_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    client.get.return_value["head"]["sha"] = initial_sha
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", flag])

    assert result.exit_code == 1
    assert "PR branch changed during fetch" in result.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == original_head
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert _git(work, "rev-parse", "feature").stdout.strip() == initial_sha


def test_patch_preserves_mail_series_and_can_be_applied_with_git_am(checkout_repo):
    work, _, latest_sha, client = checkout_repo
    _git(work, "fetch", "origin", "feature")
    patch_text = _git(work, "format-patch", "--stdout", "--binary", "main..FETCH_HEAD").stdout
    client.request.return_value = patch_text

    result = CliRunner().invoke(main, ["pr", "diff", "42", "-R", "owner/repo", "--patch"])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == patch_text.encode("utf-8")
    client.request.assert_called_once_with(
        "GET", "/repos/owner/repo/pulls/42/patch", accept="text/plain", response_format="text"
    )
    _git(work, "am", input_text=result.output)
    assert _git(work, "rev-parse", "HEAD^{tree}").stdout == _git(work, "rev-parse", f"{latest_sha}^{{tree}}").stdout
    assert _git(work, "log", "-2", "--format=%s").stdout.splitlines() == ["Latest PR commit", "First PR commit"]


def test_patch_with_real_escape_bytes_round_trips_through_git_am(checkout_repo):
    work, _, latest_sha, client = checkout_repo
    _git(work, "fetch", "origin", "feature")
    _git(work, "checkout", "--detach", latest_sha)
    content = b"ANSI \x1b[31mred\x1b[0m\nOSC \x1b]0;untrusted title\x07\n"
    (work / "file.txt").write_bytes(content)
    _git(work, "commit", "-am", "Preserve escape bytes")
    expected_tree = _git(work, "rev-parse", "HEAD^{tree}").stdout
    patch_bytes = subprocess.run(
        ["git", "format-patch", "--stdout", "--binary", "main..HEAD"],
        cwd=work,
        capture_output=True,
        check=True,
    ).stdout
    assert b"\x1b[31m" in patch_bytes and b"\x1b]0;" in patch_bytes
    client.request.return_value = patch_bytes.decode("utf-8")
    _git(work, "checkout", "main")

    result = CliRunner().invoke(main, ["pr", "diff", "42", "-R", "owner/repo", "--patch"])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == patch_bytes
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "am"],
        cwd=work,
        input=result.stdout_bytes,
        capture_output=True,
        check=True,
    )
    assert _git(work, "rev-parse", "HEAD^{tree}").stdout == expected_tree
    assert (work / "file.txt").read_bytes() == content
    assert _git(work, "log", "-3", "--format=%s").stdout.splitlines() == [
        "Preserve escape bytes",
        "Latest PR commit",
        "First PR commit",
    ]
