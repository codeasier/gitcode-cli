"""Real Git routing checks use synthetic repositories and file transport only."""

import os
import subprocess
from dataclasses import replace

import pytest

from gitcode_cli import pr_git
from gitcode_cli.errors import GCError


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    # Never inherit a caller's repository, config, credentials, hooks or network
    # transports. Both remotes deliberately contain the SAME ref and commit.
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    source, other, local = (tmp_path / name for name in ("source.git", "other.git", "local"))

    def git(*args, cwd=local, check=True):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=", *map(str, args)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )

    git("init", "--template=", "--bare", source, cwd=tmp_path)
    git("init", "--template=", "--bare", other, cwd=tmp_path)
    git("init", "--template=", local, cwd=tmp_path)
    git("config", "core.hooksPath", "")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "seed"
    )
    sha = git("rev-parse", "HEAD").stdout.strip()
    for remote in (source, other):
        git("push", remote, "HEAD:refs/heads/feature")
    monkeypatch.chdir(local)
    head = pr_git.PRHead(source.as_uri(), "feature", sha)
    # Only replace the API-to-Git boundary with a local transport. The routing,
    # lease, fetch, verification and checkout implementation all remain real.
    monkeypatch.setattr(pr_git, "resolve_head", lambda _: head)
    return git, source, other, local, head


def run_operation(operation):
    if operation == "push":
        return pr_git.delete_head({"head": {"repo": {}}})
    return pr_git.checkout_head({}, "reviewed-feature")


def assert_branch(git, repository, sha):
    assert git("rev-parse", "--verify", "refs/heads/feature", cwd=repository).stdout.strip() == sha


@pytest.mark.parametrize("operation", ["push", "fetch"])
@pytest.mark.parametrize("rewrite", ["insteadOf", "pushInsteadOf"])
@pytest.mark.parametrize("scope", ["local", "environment"])
def test_effective_destination_rewrites_are_refused(repositories, monkeypatch, operation, rewrite, scope):
    git, source, other, local, head = repositories
    key = f"url.{other.as_uri()}.{rewrite}"
    if scope == "local":
        git("config", key, source.as_uri())
    else:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", key)
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", source.as_uri())
    before = (local / ".git" / "config").read_bytes()
    if operation == "fetch" and rewrite == "pushInsteadOf":
        assert run_operation(operation) == "reviewed-feature"
        assert str(source) in (local / ".git" / "FETCH_HEAD").read_text()
    else:
        with pytest.raises(GCError, match="URL rewriting"):
            run_operation(operation)
        assert not (local / ".git" / "FETCH_HEAD").exists()
    assert_branch(git, source, head.sha)
    assert_branch(git, other, head.sha)
    assert (local / ".git" / "config").read_bytes() == before


@pytest.mark.parametrize("operation", ["push", "fetch"])
@pytest.mark.parametrize("rewrite", ["insteadOf", "pushInsteadOf"])
def test_longest_match_is_checked_instead_of_only_a_broad_prefix(repositories, operation, rewrite):
    git, source, other, _, head = repositories
    # A broad identity rewrite must not hide a more specific wrong repository.
    prefix = source.parent.as_uri() + "/"
    git("config", f"url.{prefix}.{rewrite}", prefix)
    git("config", f"url.{other.as_uri()}.{rewrite}", source.as_uri())
    if operation == "fetch" and rewrite == "pushInsteadOf":
        assert run_operation(operation) == "reviewed-feature"
    else:
        with pytest.raises(GCError, match="URL rewriting"):
            run_operation(operation)
    assert_branch(git, source, head.sha)
    assert_branch(git, other, head.sha)


@pytest.mark.parametrize("operation", ["push", "fetch"])
@pytest.mark.parametrize("scope", ["local", "environment"])
def test_checked_destination_stays_pinned_when_rewrites_change(repositories, monkeypatch, operation, scope):
    git, source, other, local, head = repositories
    original = pr_git._git
    changed = False

    def change_after_check(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if "get-url" in args:
            assert result.stdout.splitlines() == [source.as_uri()]
            # Install multiple rewrite families, including a broad alias-prefix
            # rule. Pinning must select its exact alias and never rewrite twice.
            rules = [
                (f"url.{other.as_uri()}.insteadOf", source.as_uri()),
                (f"url.{other.as_uri()}.pushInsteadOf", source.as_uri()),
                (f"url.{other.as_uri()}.insteadOf", "gc-pr-"),
                (f"url.{other.as_uri()}.pushInsteadOf", "gc-pr-"),
            ]
            if scope == "local":
                for key, value in rules:
                    git("config", "--add", key, value)
            else:
                monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(rules)))
                for index, (key, value) in enumerate(rules):
                    monkeypatch.setenv(f"GIT_CONFIG_KEY_{index}", key)
                    monkeypatch.setenv(f"GIT_CONFIG_VALUE_{index}", value)
            changed = True
        return result

    monkeypatch.setattr(pr_git, "_git", change_after_check)
    assert run_operation(operation) == ("feature" if operation == "push" else "reviewed-feature")
    assert changed
    assert_branch(git, other, head.sha)
    if operation == "push":
        assert git("show-ref", "--verify", "refs/heads/feature", cwd=source, check=False).returncode != 0
    else:
        assert_branch(git, source, head.sha)
        assert str(source) in (local / ".git" / "FETCH_HEAD").read_text()
        assert git("rev-parse", "HEAD").stdout.strip() == head.sha
    # No synthetic remote is ever persisted, even after successful operations.
    assert git("remote").stdout == ""


@pytest.mark.parametrize("field", ["url", "pushurl", "receivepack", "mirror"])
def test_private_remote_collision_fails_closed(repositories, monkeypatch, field):
    git, source, other, _, head = repositories
    monkeypatch.setattr(pr_git.secrets, "token_hex", lambda _: "fixed")
    git("config", f"remote.gc-pr-fixed.{field}", "true" if field == "mirror" else other.as_uri())
    with pytest.raises(GCError, match="private Git remote"):
        run_operation("push")
    assert_branch(git, source, head.sha)
    assert_branch(git, other, head.sha)


def test_private_remote_config_probe_failure_never_pushes(repositories, monkeypatch):
    git, source, other, _, head = repositories
    original = pr_git._git

    def failed_probe(*args, **kwargs):
        if args[0] == "config":
            return subprocess.CompletedProcess(args, 2, "", "synthetic config failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(pr_git, "_git", failed_probe)
    with pytest.raises(GCError, match="private Git remote"):
        run_operation("push")
    assert_branch(git, source, head.sha)
    assert_branch(git, other, head.sha)


def test_pinned_push_keeps_explicit_sha_lease(repositories, monkeypatch):
    git, source, other, _, head = repositories
    monkeypatch.setattr(pr_git, "resolve_head", lambda _: replace(head, sha="0" * 40))
    with pytest.raises(GCError, match="Git operation failed"):
        run_operation("push")
    assert_branch(git, source, head.sha)
    assert_branch(git, other, head.sha)
