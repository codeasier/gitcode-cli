"""Isolated installed-entrypoint harness; no credentials or real network access."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path

import pytest

NETWORK_BLOCKED = "Network disabled in offline CLI e2e"


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def gc_env(isolated_home: Path, tmp_path: Path) -> dict[str, str]:
    """Allowlist the child environment instead of copying ambient tokens/config."""
    guard = tmp_path / "network_guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys\n"
        "def deny_network(event, args):\n"
        "    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname',\n"
        "                 'socket.gethostbyaddr', 'socket.sendto'}:\n"
        f"        raise RuntimeError({NETWORK_BLOCKED!r})\n"
        "sys.addaudithook(deny_network)\n",
        encoding="utf-8",
    )
    temp = tmp_path / "tmp"
    temp.mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update(
        {
            "PATH": os.defpath,
            "HOME": str(isolated_home),
            "USERPROFILE": str(isolated_home),
            "XDG_CONFIG_HOME": str(isolated_home / ".config"),
            "TMPDIR": str(temp),
            "TMP": str(temp),
            "TEMP": str(temp),
            "COLUMNS": "120",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(guard),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CEILING_DIRECTORIES": str(tmp_path),
        }
    )
    return env


@pytest.fixture(scope="session")
def installed_cli() -> dict[str, str]:
    """Use this interpreter's scripts directory, never an ambient `gc` binary."""
    distribution = importlib.metadata.distribution("pygitcode")
    entrypoints = {entry.name: entry.value for entry in distribution.entry_points if entry.group == "console_scripts"}
    scripts = sysconfig.get_path("scripts")
    commands = {}
    for name in ("gc", "gitcode"):
        assert entrypoints[name] == "gitcode_cli.cli:main"
        executable = shutil.which(name, path=scripts)
        assert executable is not None, f"Install this checkout with python -m pip install -e '.[dev]': missing {name}"
        commands[name] = executable
    return commands


@pytest.fixture
def run_gc(installed_cli: dict[str, str], gc_env: dict[str, str], tmp_path: Path):
    """Run a real console script outside the checkout; preserve both streams."""
    work = tmp_path / "work"
    work.mkdir()

    def run(args, *, entrypoint="gc", input=None, env=None, cwd=None):
        result = subprocess.run(
            [installed_cli[entrypoint], *args],
            cwd=cwd or work,
            env={**gc_env, **(env or {})},
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        assert NETWORK_BLOCKED not in result.stdout + result.stderr, "Offline scenario attempted a network request"
        return result

    return run
