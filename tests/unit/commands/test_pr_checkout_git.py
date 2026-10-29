"""Exercise PR checkout flags against disposable local Git repositories, without API access."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main


def _git(path, *args, check=True):
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=path,
        capture_output=True,
        text=True,
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
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
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
    _git(work, "checkout", "main")
    (seed / "file.txt").write_text("latest\n")
    _git(seed, "commit", "-am", "Latest PR commit")
    latest_sha = _git(seed, "rev-parse", "HEAD").stdout.strip()
    _git(seed, "push", str(tmp_path / "origin.git"), "feature")
    client = MagicMock()
    client.get.return_value = {"head": {"ref": "feature", "sha": latest_sha}}
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


@pytest.mark.parametrize("flag", ["--force", "--detach"])
def test_checkout_refuses_head_mismatch_before_changing_checkout(checkout_repo, flag):
    work, initial_sha, _, client = checkout_repo
    original_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    client.get.return_value["head"]["sha"] = initial_sha
    result = CliRunner().invoke(main, ["pr", "checkout", "42", "-R", "owner/repo", flag])

    assert result.exit_code == 1
    assert "Fetched head does not match the PR head" in result.output
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == original_head
    assert _git(work, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert _git(work, "rev-parse", "feature").stdout.strip() == initial_sha
