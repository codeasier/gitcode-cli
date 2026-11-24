"""Offline installed-entrypoint acceptance for checkout-local defaults."""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
def test_installed_set_default_needs_no_auth_or_network(run_gc, gc_env, isolated_home, tmp_path, entrypoint):
    git = shutil.which("git", path=gc_env["PATH"])
    assert git is not None
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def local_git(*args):
        return subprocess.run(
            [git, *args], cwd=checkout, env=gc_env, check=True, capture_output=True, text=True, timeout=10
        ).stdout

    local_git("init", "-q")
    local_git("remote", "add", "origin", "https://github.com/owner/repo.git")
    local_git("remote", "add", "upstream", "git@gitcode.com:owner/repo.git")
    before = local_git("config", "--local", "--list")

    def invoke(*args):
        return run_gc(["repo", "set-default", *args], cwd=checkout, entrypoint=entrypoint)

    result = invoke("upstream")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    result = invoke("--view")
    assert (result.returncode, result.stdout, result.stderr) == (0, "owner/repo\n", "")
    assert invoke("--unset").returncode == 0
    assert local_git("config", "--local", "--list") == before
    assert not (isolated_home / ".config" / "gc" / "config.json").exists()
