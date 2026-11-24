"""Use real, file-only Git to check ordinary clone behavior without provider access."""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.e2e


def test_no_upstream_uses_one_ordinary_clone_and_preserves_existing_files(gc_env, run_gc, tmp_path):
    git = shutil.which("git", path=gc_env["PATH"])
    assert git is not None
    source = tmp_path / "source"
    source.mkdir()
    url = "https://gitcode.com/fixture/fork.git"
    env = {
        **gc_env,
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{source.as_uri()}.insteadOf",
        "GIT_CONFIG_VALUE_0": url,
    }

    def local_git(cwd, *args):
        return subprocess.run(
            [git, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=15, check=True
        ).stdout.strip()

    local_git(source, "-c", "init.defaultBranch=main", "init", "-q")
    (source / "README").write_text("from the child\n", encoding="utf-8")
    local_git(source, "add", "README")
    local_git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    child = tmp_path / "checkout"
    result = run_gc(["repo", "clone", "fixture/fork", str(child), "--no-upstream", "--", "--depth", "1"], env=env)
    assert result.returncode == 0, result.stderr
    assert (child / "README").read_bytes() == (source / "README").read_bytes()
    assert local_git(child, "remote") == "origin"
    assert local_git(child, "config", "--local", "--get", "remote.origin.url") == url
    assert local_git(child, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/main"
    assert local_git(child, "rev-parse", "--is-shallow-repository") == "true"

    # The destination now contains user data. Git's native refusal is propagated;
    # gc must not delete/recreate the destination or clean up its local changes.
    marker = child / "README"
    marker.write_text("my uncommitted edits\n", encoding="utf-8")
    before = (child / ".git" / "config").read_bytes()
    expected = subprocess.run(
        [git, "clone", url, str(child)], cwd=tmp_path, env=env, capture_output=True, timeout=15, check=False
    )
    assert expected.returncode != 0
    refused = run_gc(["repo", "clone", "--no-upstream", "fixture/fork", str(child)], env=env)
    assert refused.returncode == expected.returncode
    assert (child / ".git" / "config").read_bytes() == before
    assert marker.read_text(encoding="utf-8") == "my uncommitted edits\n"
