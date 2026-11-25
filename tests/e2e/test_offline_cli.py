"""Process smoke tests, not full gh compatibility or live API acceptance."""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

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


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        (["--help"], 0, "Inspect gc ? gh compatibility".encode("gbk")),
        (["--unknown-宝↔"], 2, "--unknown-宝?".encode("gbk")),
        (["binary-test"], 0, bytes.fromhex("00ff80a2")),
        (["json-test"], 0, {"title": "宝?"}),
    ],
)
def test_windows_eager_cli_messages_survive_a_gbk_pipe(gc_env, tmp_path, args, code, message):
    # Real redirected GBK streams on every CI platform; only the CLI's platform check is simulated.
    source = Path(__file__).resolve().parents[2] / "src"
    entrypoint = """
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv.pop(1))
from gitcode_cli import cli
from gitcode_cli.utils import safe_echo

assert sys.stdout.encoding.lower() == "gbk" and not sys.stdout.isatty()
assert sys.stderr.encoding.lower() == "gbk" and not sys.stderr.isatty()
# Python otherwise defaults stderr to backslashreplace independently of PYTHONIOENCODING.
sys.stderr.reconfigure(errors="strict")
cli.sys = SimpleNamespace(platform="win32", stdout=sys.stdout, stderr=sys.stderr)

@cli.main.command("binary-test")
def binary_test():
    sys.stdout.buffer.write(bytes.fromhex("00ff80a2"))

@cli.main.command("json-test")
def json_test():
    safe_echo(json.dumps({"title": "宝📚"}, ensure_ascii=False))

cli.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", entrypoint, str(source), *args],
        cwd=tmp_path,
        env={**gc_env, "PYTHONIOENCODING": "gbk:strict"},
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == code, result.stderr
    output = result.stderr if code else result.stdout
    if args == ["binary-test"]:
        assert output == message
    elif args == ["json-test"]:
        assert json.loads(output.decode("gbk")) == message
    else:
        assert message in output
        output.decode("gbk")  # The whole stream must still use the initial codec.
    assert b"Traceback" not in result.stderr


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
        (["auth", "status", "--json", "invalid"], "Available JSON fields", 2),
        (["issue", "list", "-R", "invalid"], "Invalid repo format", 1),
        (["not-a-command"], "No such command", 2),
    ],
)
def test_local_errors_have_stderr_and_exit_code(run_gc, args, message, code):
    result = run_gc(args, input="")
    assert result.returncode == code
    assert result.stdout == ""
    assert message in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
def test_logged_out_auth_json_is_machine_readable_without_network(run_gc, entrypoint):
    result = run_gc(["auth", "status", "--json", "hosts"], entrypoint=entrypoint, env={"GC_GH_PROXY_ACTIVE": "1"})

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"hosts": {}}
    assert result.stderr == ""


def test_missing_repository_fails_locally(run_gc):
    if shutil.which("git") is None:
        pytest.skip("Git is required for local repository inference")
    result = run_gc(["issue", "list"], input="")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Unable to infer repo" in result.stderr
    assert "Traceback" not in result.stderr


def test_subprocess_environment_drops_ambient_credentials(gc_env, isolated_home):
    assert "GC_TOKEN" not in gc_env
    assert "GH_TOKEN" not in gc_env
    assert "GITHUB_TOKEN" not in gc_env
    assert "PYTHONHOME" not in gc_env
    assert "GC_GH_PROXY_ACTIVE" not in gc_env
    assert gc_env["HOME"] == str(isolated_home)
    assert gc_env["XDG_CONFIG_HOME"] == str(isolated_home / ".config")
    assert gc_env["PYTHONIOENCODING"] == "utf-8"


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


@pytest.mark.parametrize(
    "proxy_env",
    [
        {"NO_PROXY": "[::1]"},
        {"NO_PROXY": "localhost", "HTTPS_PROXY": "http://user:fake-proxy-password@proxy.invalid:bad-port"},
        {"NO_PROXY": "localhost", "HTTPS_PROXY": "unsupported://fake-user:fake-password@proxy.invalid:8080"},
    ],
    ids=["bracketed-no-proxy", "credential-bearing-proxy", "unsupported-scheme"],
)
def test_invalid_proxy_environment_fails_without_network_or_traceback(run_gc, proxy_env):
    result = run_gc(["issue", "view", "1129", "-R", "openeuler/community", "--json", "number"], env=proxy_env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "error: Invalid HTTP proxy configuration. Check HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, and NO_PROXY.\n"
    )
