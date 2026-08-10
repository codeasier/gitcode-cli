from __future__ import annotations

import os
import subprocess

import pytest

from gitcode_cli.gh_proxy import (
    ProxyError,
    _exec,
    _explicit_repo,
    dispatch,
    find_real_gh,
    select_target,
    validate_gitcode_command,
)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["issue", "list", "-R", "gitcode.com/o/r"], "gitcode.com/o/r"),
        (["-Rgithub.com/o/r", "pr", "view", "1"], "github.com/o/r"),
        (["pr", "list", "--repo=gitcode.com/o/r"], "gitcode.com/o/r"),
        (["issue", "list"], None),
    ],
)
def test_explicit_repo(args, expected):
    assert _explicit_repo(args) == expected


def test_target_override_has_highest_priority(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "github.com")
    assert select_target(["-R", "github.com/o/r"], {"GC_GH_TARGET": "gitcode"}) == "gitcode"


def test_invalid_target_override_fails():
    with pytest.raises(ProxyError, match="GC_GH_TARGET"):
        select_target([], {"GC_GH_TARGET": "other"})


@pytest.mark.parametrize(
    ("repo", "expected"),
    [
        ("gitcode.com/o/r", "gitcode"),
        ("github.com/o/r", "github"),
        ("code.example.com/o/r", "github"),
    ],
)
def test_explicit_host_routes_before_remote(monkeypatch, repo, expected):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com")
    assert select_target(["issue", "list", "-R", repo], {}) == expected


def test_custom_gitcode_host(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "code.example.com")
    assert select_target([], {"GC_GITCODE_HOSTS": "code.example.com,gitcode.internal"}) == "gitcode"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("gitcode.com", "gitcode"),
        ("ssh.gitcode.com", "gitcode"),
        ("git@ssh.gitcode.com:443", "gitcode"),
        ("codeasier@gitcode.com", "gitcode"),
        ("gitcode.com:443", "gitcode"),
        ("git@github.com", "github"),
    ],
)
def test_host_with_userinfo_or_port_is_normalized(monkeypatch, host, expected):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: host)
    assert select_target([], {}) == expected


def test_unqualified_repo_uses_remote(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com")
    assert select_target(["-R", "o/r", "issue", "list"], {}) == "gitcode"


def test_unknown_context_defaults_to_github(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    assert select_target(["issue", "list"], {}) == "github"


@pytest.mark.parametrize(
    "args",
    [
        ["issue", "list"],
        ["issue", "ls"],
        ["pr", "new"],
        ["auth", "login"],
        ["issue", "--help"],
        ["--version"],
    ],
)
def test_supported_gitcode_commands(args):
    validate_gitcode_command(args)


@pytest.mark.parametrize("args", [["api", "repos/o/r"], ["issue", "lock", "1"], ["repo", "clone", "o/r"]])
def test_unsupported_gitcode_commands_fail_closed(args):
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(args)


def test_real_gh_override(tmp_path):
    real_gh = tmp_path / "gh-real"
    real_gh.write_text("#!/bin/sh\n", encoding="utf-8")
    real_gh.chmod(0o755)
    assert find_real_gh({"GC_REAL_GH": str(real_gh)}) == str(real_gh.resolve())


def test_real_gh_override_must_not_be_shim(tmp_path):
    shim = tmp_path / "gh"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    shim.chmod(0o755)
    with pytest.raises(ProxyError, match="proxy itself"):
        find_real_gh({"GC_REAL_GH": str(shim), "GC_GH_SHIM": str(shim)})


def test_find_real_gh_excludes_shim_directory(tmp_path):
    shim_dir = tmp_path / "shim"
    real_dir = tmp_path / "real"
    shim_dir.mkdir()
    real_dir.mkdir()
    shim = shim_dir / "gh"
    real = real_dir / "gh"
    for executable in (shim, real):
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
    env = {"GC_GH_SHIM": str(shim), "PATH": os.pathsep.join([str(shim_dir), str(real_dir)])}
    assert find_real_gh(env) == str(real.resolve())


def test_find_real_gh_reports_missing_binary(tmp_path):
    with pytest.raises(ProxyError, match="Unable to find"):
        find_real_gh({"PATH": str(tmp_path)})


def test_dispatch_forwards_gitcode_args_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "gitcode")
    monkeypatch.setattr("gitcode_cli.gh_proxy.shutil.which", lambda command, path=None: "/bin/gc")
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda executable, args: calls.append((executable, args)) or 7)
    args = ["issue", "view", "1", "--comments"]
    assert dispatch(args, {"PATH": "/bin"}) == 7
    assert calls == [("/bin/gc", args)]


def test_dispatch_forwards_github_args_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "github")
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda env: "/usr/bin/gh")
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda executable, args: calls.append((executable, args)) or 9)
    args = ["repo", "view", "github.com/o/r"]
    assert dispatch(args, {}) == 9
    assert calls == [("/usr/bin/gh", args)]


def test_posix_exec_replaces_process_with_unchanged_args(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.os.name", "posix")
    monkeypatch.setattr("gitcode_cli.gh_proxy.os.execv", lambda executable, args: calls.append((executable, args)))
    assert _exec("/usr/bin/gh", ["issue", "list"]) == 0
    assert calls == [("/usr/bin/gh", ["/usr/bin/gh", "issue", "list"])]


def test_dispatch_reports_missing_gc(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "gitcode")
    monkeypatch.setattr("gitcode_cli.gh_proxy.shutil.which", lambda command, path=None: None)
    with pytest.raises(ProxyError, match="Unable to find gc"):
        dispatch(["issue", "list"], {"PATH": ""})


def test_origin_host_reads_git_remote(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "git@gitcode.com:o/r.git\n", ""),
    )
    assert _origin_host() == "gitcode.com"


def test_origin_host_reads_ssh_remote_with_custom_port(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "ssh://git@gitcode.com:2222/o/r.git\n", ""),
    )
    assert _origin_host() == "gitcode.com"


def test_origin_host_reads_gitcode_ssh_endpoint_with_custom_port(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "ssh://git@ssh.gitcode.com:443/o/r.git\n", ""),
    )
    assert _origin_host() == "ssh.gitcode.com"
    assert select_target([], {}) == "gitcode"


def test_origin_host_ignores_git_failure(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "git")),
    )
    assert _origin_host() is None
