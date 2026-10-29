"""Process smoke tests, not full gh compatibility or live API acceptance."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
@pytest.mark.parametrize("command", [[], ["auth"], ["issue"], ["issue", "create"], ["pr"], ["pr", "create"]])
def test_installed_entrypoint_help(run_gc, entrypoint, command):
    result = run_gc([*command, "-h"], entrypoint=entrypoint)
    assert result.returncode == 0
    assert "USAGE" in result.stdout
    assert "\x1b[" not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
@pytest.mark.parametrize("args", [["version"], ["--version"]])
def test_installed_entrypoint_version(run_gc, entrypoint, args):
    result = run_gc(args, entrypoint=entrypoint)
    assert result.returncode == 0
    assert importlib.metadata.version("pygitcode") in result.stdout
    assert "gitcode" in result.stdout
    assert result.stderr == ""


def test_auth_config_roundtrip_is_isolated(run_gc, isolated_home):
    config = isolated_home / ".config" / "gc" / "config.json"
    assert not config.exists()
    missing = run_gc(["auth", "token"])
    assert missing.returncode == 1
    assert missing.stdout == ""
    assert "No token found" in missing.stderr

    login = run_gc(["auth", "login", "--with-token"], input="synthetic-config-token\n")
    assert login.returncode == 0
    assert login.stdout == "Authentication saved.\n"
    assert login.stderr == ""
    assert json.loads(config.read_text()) == {"token": "synthetic-config-token"}

    token = run_gc(["auth", "token"])
    assert token.returncode == 0
    assert token.stdout == "synthetic-config-token\n"
    override = run_gc(["auth", "token"], env={"GC_TOKEN": "synthetic-env-token"})
    assert override.returncode == 0
    assert override.stdout == "synthetic-env-token\n"
    assert json.loads(config.read_text())["token"] == "synthetic-config-token"

    logout = run_gc(["auth", "logout"])
    assert logout.returncode == 0
    assert logout.stdout == "Logged out.\n"
    assert logout.stderr == ""
    assert json.loads(config.read_text()) == {}


@pytest.mark.parametrize(
    ("args", "message", "code"),
    [
        (["auth", "login", "--with-token"], "No token provided on stdin", 1),
        (["auth", "logout"], "Not logged in", 1),
        (["auth", "status", "--json", "hosts"], "recognized but not implemented yet", 1),
        (["issue", "list", "-R", "invalid"], "Invalid repo format", 1),
        (["issue", "list"], "Unable to infer repo", 1),
        (["not-a-command"], "No such command", 2),
    ],
)
def test_local_errors_have_stderr_and_exit_code(run_gc, args, message, code):
    result = run_gc(args, input="")
    assert result.returncode == code
    assert result.stdout == ""
    assert message in result.stderr
    assert "Traceback" not in result.stderr


def test_subprocess_environment_drops_ambient_credentials(gc_env, isolated_home):
    assert "GC_TOKEN" not in gc_env
    assert "GH_TOKEN" not in gc_env
    assert "GITHUB_TOKEN" not in gc_env
    assert "PYTHONHOME" not in gc_env
    assert "GC_GH_PROXY_ACTIVE" not in gc_env
    assert gc_env["HOME"] == str(isolated_home)
    assert gc_env["XDG_CONFIG_HOME"] == str(isolated_home / ".config")


def test_network_guard_blocks_child_before_dns(gc_env, tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.getaddrinfo('offline.invalid', 443)"],
        env=gc_env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "Network disabled in offline CLI e2e" in result.stderr
