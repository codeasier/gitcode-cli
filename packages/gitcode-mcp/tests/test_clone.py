import os
import subprocess
from pathlib import Path

import pytest

from gitcode_mcp.askpass import answer
from gitcode_mcp.clone import CloneError, clone_repository
from gitcode_mcp.config import ConfigurationError


@pytest.mark.parametrize(
    "prompt",
    [
        "Password for 'https://gitcode.com.evil.test':",
        "Password for 'https://gitcode.com@evil.test':",
        "Password for 'http://gitcode.com':",
        "Password for 'https://gitcode.com:8080':",
        "Password for 'https://gitcode.com:invalid':",
        "Password: ",
    ],
)
def test_askpass_refuses_non_gitcode_prompts(prompt):
    assert answer(prompt, "secret", "alice") is None


def test_askpass_only_answers_expected_https_prompts():
    assert answer("Username for 'https://gitcode.com':", "secret", "alice") == "alice"
    assert answer("Password for 'https://alice@gitcode.com':", "secret", "alice") == "secret"
    assert answer("unrecognized 'https://gitcode.com'", "secret", "alice") is None


def test_clone_uses_temporary_credentials_and_separate_checkout(tmp_path, monkeypatch):
    calls = []
    helper_paths = []

    def run(args, *, env, **kwargs):
        calls.append((args, env.copy()))
        if "clone" in args:
            helper = Path(env["GIT_ASKPASS"])
            helper_paths.append(helper)
            assert "clone-secret" not in helper.read_text()
            assert helper.stat().st_mode & 0o777 == 0o700
        return subprocess.CompletedProcess(args, 0, "f" * 40 if "rev-parse" in args else "", "")

    monkeypatch.setattr(subprocess, "run", run)
    value = clone_repository(
        "owner/repo",
        tmp_path / "checkout",
        branch="fix/topic",
        depth=1,
        env={
            "GITCODE_TOKEN": "clone-secret",
            "GC_TOKEN": "other-secret",
            "GITCODE_USERNAME": "alice",
            "GIT_TRACE_CURL": "1",
        },
    )
    assert value["execution_scope"] == "local_process"
    assert value["head_sha"] == "f" * 40
    assert value["clone_url"] == "https://gitcode.com/owner/repo.git"
    clone_args, clone_env = next(call for call in calls if "clone" in call[0])
    assert "--no-checkout" in clone_args
    assert "credential.helper=" in clone_args
    assert "http.followRedirects=false" in clone_args
    assert clone_env["GITCODE_CLONE_TOKEN"] == "clone-secret"
    for args, env in calls:
        assert not any("secret" in arg for arg in args)
        assert not {"GITCODE_TOKEN", "GC_TOKEN", "GIT_TRACE_CURL"} & env.keys()
        if "clone" not in args:
            assert "GITCODE_CLONE_TOKEN" not in env
    assert all(not path.exists() for path in helper_paths)


def test_existing_destination_is_untouched(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "important.txt"
    sentinel.write_text("keep")
    with pytest.raises(CloneError, match="already exists"):
        clone_repository("owner/repo", destination, env={})
    assert sentinel.read_text() == "keep"


def test_pat_helper_ignores_worktree_and_pythonpath_modules(tmp_path, monkeypatch):
    """An untrusted checkout must not shadow the credential handler's import."""
    shadow = tmp_path / "untrusted"
    package = shadow / "gitcode_mcp"
    package.mkdir(parents=True)
    marker = shadow / "executed"
    (package / "__init__.py").write_text("")
    (package / "askpass.py").write_text(
        "from pathlib import Path\nPath('executed').write_text('untrusted code ran')\n"
    )
    real_run = subprocess.run

    def run(args, *, env, **kwargs):
        if "clone" in args:
            helper = real_run(
                [env["GIT_ASKPASS"], "Password for 'https://alice@gitcode.com':"],
                env=env,
                cwd=shadow,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert helper.returncode == 0
            assert helper.stdout.strip() == "temporary-test-pat"
            assert not marker.exists()
        return subprocess.CompletedProcess(args, 0, "f" * 40 if "rev-parse" in args else "", "")

    monkeypatch.setattr(subprocess, "run", run)
    clone_repository(
        "owner/repo",
        tmp_path / "checkout",
        env={
            "GITCODE_TOKEN": "temporary-test-pat",
            "GITCODE_USERNAME": "alice",
            "PYTHONPATH": str(shadow),
        },
    )


def test_broken_destination_symlink_is_not_followed(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(CloneError, match="already exists"):
        clone_repository("owner/repo", link, env={})


def test_clone_enforces_allowlist_and_does_not_guess_pat_username(tmp_path):
    with pytest.raises(ConfigurationError, match="not in"):
        clone_repository(
            "owner/repo", tmp_path / "new", env={"GITCODE_MCP_ALLOWED_REPOS": "other/repo"}
        )
    with pytest.raises(ConfigurationError, match="GITCODE_USERNAME"):
        clone_repository("owner/repo", tmp_path / "new", env={"GITCODE_TOKEN": "secret"})
    assert not (tmp_path / "new").exists()


def test_git_error_does_not_expose_captured_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 128, "", "secret remote response"),
    )
    with pytest.raises(CloneError) as error:
        clone_repository("owner/repo", tmp_path / "new", env={})
    assert "secret" not in str(error.value)
    assert (tmp_path / "new").exists()  # Partial state is never recursively deleted.


def test_ssh_does_not_inherit_pat(tmp_path, monkeypatch):
    def run(args, *, env, **kwargs):
        assert "GITCODE_TOKEN" not in env
        assert "GITCODE_CLONE_TOKEN" not in env
        if "clone" in args:
            assert "git@gitcode.com:owner/repo.git" in args
        return subprocess.CompletedProcess(args, 0, "f" * 40 if "rev-parse" in args else "", "")

    monkeypatch.setattr(subprocess, "run", run)
    clone_repository("owner/repo", tmp_path / "ssh", ssh=True, env={"GITCODE_TOKEN": "secret"})


def test_real_git_checkout_preserves_branch(tmp_path, monkeypatch):
    """Exercise Git itself using a local fixture instead of a live GitCode account."""
    real_run = subprocess.run
    source = tmp_path / "source"
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith("GITCODE_") or key == "GC_TOKEN":
            environment.pop(key)
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    real_run(["git", "init", "-q", "-b", "main", str(source)], check=True, env=environment)
    (source / "hello.txt").write_text("hello\n")
    real_run(["git", "-C", str(source), "add", "hello.txt"], check=True, env=environment)
    real_run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
        env=environment,
    )

    def local_transport(args, **kwargs):
        args = [str(source) if arg == "https://gitcode.com/owner/repo.git" else arg for arg in args]
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", local_transport)
    destination = tmp_path / "clone"
    result = clone_repository("owner/repo", destination, env=environment)
    assert (destination / "hello.txt").read_text() == "hello\n"
    assert len(result["head_sha"]) == 40
    branch = real_run(
        ["git", "-C", str(destination), "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert branch.stdout.strip() == "main"
