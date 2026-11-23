from __future__ import annotations

import os
import subprocess
import sys

import pytest

from gitcode_cli.gh_proxy import (
    ProxyError,
    _exec,
    _explicit_repos,
    _positional_repo_host,
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
    assert _explicit_repos(args) == ([expected] if expected else [])


def test_target_override_has_highest_priority(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "github.com")
    assert select_target(["pr", "view", "1"], {"GC_GH_TARGET": "gitcode"}) == "gitcode"


@pytest.mark.parametrize(
    "argv",
    [
        ["repo", "sync", "-b", "github.com/not/repo", "gitcode.com/o/r"],
        ["issue", "develop", "-l", "https://gitcode.com/o/r/issues/1"],
        ["pr", "merge", "--match-head-commit", "ignored", "https://gitcode.com/o/r/pull/3"],
    ],
)
def test_scoped_commands_do_not_route_by_flag_values(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "github.com")
    assert select_target(argv, {}) == "gitcode"


@pytest.mark.parametrize("credential", [["--token", "synthetic-marker"], ["--token=synthetic-marker"]])
@pytest.mark.parametrize("env", [{}, {"GC_GH_TARGET": "gitcode"}, {"GC_GH_TARGET": "github"}])
def test_proxy_rejects_global_token_option_without_routing_or_reflection(monkeypatch, credential, env):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("origin should not be inspected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: pytest.fail("proxy should not dispatch"))
    with pytest.raises(ProxyError, match="does not accept --token") as exc:
        dispatch(["-R", "gitcode.com/o/r", *credential, "auth", "token"], env)
    assert "synthetic-marker" not in str(exc.value)


@pytest.mark.parametrize("env", [{}, {"GC_GH_TARGET": "gitcode"}])
def test_proxy_api_refusal_never_reflects_endpoint(monkeypatch, env):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com")
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: pytest.fail("proxy should not dispatch"))
    with pytest.raises(ProxyError, match="use gc api directly") as exc:
        dispatch(["api", "user?access_token=synthetic-marker"], env)
    assert "synthetic-marker" not in str(exc.value)


@pytest.mark.parametrize(
    "args",
    [
        ["help", "api"],
        ["help", "api", "user?access_token=synthetic-marker"],
        ["help", "api", "repos/o/r/issues", "-X", "POST", "--input"],
        ["help", "auth", "--token=synthetic-marker"],
        ["help", "--", "issue"],
    ],
)
def test_gitcode_help_cannot_dispatch_direct_only_api_or_consume_help_flag(monkeypatch, args):
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *argv: pytest.fail("proxy should not dispatch"))
    with pytest.raises(ProxyError) as exc:
        dispatch(args, {"GC_GH_TARGET": "gitcode"})
    assert "synthetic-marker" not in str(exc.value)


def test_unknown_gitcode_command_refusal_does_not_echo_arguments():
    with pytest.raises(ProxyError, match="refusing to fall back") as exc:
        validate_gitcode_command(["synthetic-marker", "literal-argument"])
    assert "synthetic-marker" not in str(exc.value) and "literal-argument" not in str(exc.value)


def test_proxy_global_token_guard_does_not_block_native_token_command_or_comment_text(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com")
    assert select_target(["auth", "token"], {}) == "gitcode"
    assert select_target(["pr", "review", "1", "--comment", "--body", "--token"], {}) == "gitcode"
    validate_gitcode_command(["auth", "token"])
    validate_gitcode_command(["pr", "review", "1", "--comment", "--body", "--token"])


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


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["repo", "view", "github.com/o/r"], "github.com"),
        (["repo", "view", "gitcode.com/o/r"], "gitcode.com"),
        (["repo", "clone", "https://github.com/o/r"], "github.com"),
        (["repo", "clone", "https://gitcode.com/o/r.git"], "gitcode.com"),
        (["repo", "fork", "git@gitcode.com:o/r.git"], "gitcode.com"),
        (["repo", "edit", "github.com/o/r", "-d", "x"], "github.com"),
        (["repo", "delete", "gitcode.com/o/r"], "gitcode.com"),
        (["repo", "sync", "github.com/o/r"], "github.com"),
        # Positionals that cannot carry a host return None
        (["repo", "view", "o/r"], None),
        (["repo", "list", "owner"], None),
        (["repo", "rename", "new-name"], None),
        (["issue", "view", "github.com/o/r"], None),
        (["repo", "view"], None),
    ],
)
def test_positional_repo_host_extracts_host_from_repository_arg(args, expected):
    assert _positional_repo_host(args) == expected


def test_positional_repo_host_routes_before_origin(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com")
    assert select_target(["repo", "view", "github.com/o/r"], {}) == "github"
    assert select_target(["repo", "clone", "gitcode.com/o/r"], {}) == "gitcode"


def test_positional_owner_repo_falls_back_to_origin(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "github.com")
    assert select_target(["repo", "view", "o/r"], {}) == "github"
    assert select_target(["repo", "clone", "o/r"], {}) == "github"


def test_repo_flag_and_positional_cannot_select_opposite_backends(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit conflict must win"))
    with pytest.raises(ProxyError, match="Explicit target hosts conflict"):
        select_target(["repo", "view", "github.com/o/r", "-R", "gitcode.com/a/b"], {})


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
        ["repo"],
        ["repo", "view"],
        ["repo", "list"],
        ["repo", "list", "owner"],
        ["repo", "clone", "o/r"],
        ["repo", "fork", "o/r"],
        ["repo", "edit", "o/r", "-d", "desc"],
        ["repo", "delete", "o/r", "--yes"],
        ["repo", "rename", "o/r", "new-name", "-y"],
        ["repo", "sync", "o/r"],
        ["repo", "create", "name", "--public"],
        ["help"],
        ["help", "issue"],
        ["issue", "--help"],
        ["--version"],
    ],
)
def test_supported_gitcode_commands(args):
    validate_gitcode_command(args)


@pytest.mark.parametrize(
    "args", [["api", "repos/o/r"], ["issue", "lock", "1"], ["repo", "deploy-key", "list"], ["repo", "autolink", "list"]]
)
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
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy._exec",
        lambda executable, args, env: calls.append((executable, args, env)) or 7,
    )
    args = ["issue", "view", "1", "--comments"]
    assert dispatch(args, {"PATH": "/bin"}) == 7
    assert calls == [
        (
            sys.executable,
            ["-m", "gitcode_cli.cli", *args],
            {"PATH": "/bin", "GC_GH_PROXY_ACTIVE": "1", "GC_GH_PROXY_TARGET": "gitcode"},
        )
    ]


def test_dispatch_translates_gitcode_help_command(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "gitcode")
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy._exec",
        lambda executable, args, env: calls.append((executable, args, env)) or 0,
    )

    assert dispatch(["help", "issue"], {}) == 0
    assert calls[0][1] == ["-m", "gitcode_cli.cli", "issue", "--help"]


def test_dispatch_forwards_github_args_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "github")
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda env: "/usr/bin/gh")
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy._exec",
        lambda executable, args, env: calls.append((executable, args, env)) or 9,
    )
    args = ["repo", "view", "github.com/o/r"]
    assert dispatch(args, {}) == 9
    assert calls == [("/usr/bin/gh", args, {})]


def test_posix_exec_replaces_process_with_unchanged_args(monkeypatch):
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy.os.name", "posix")
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.os.execve",
        lambda executable, args, env: calls.append((executable, args, env)),
    )
    assert _exec("/usr/bin/gh", ["issue", "list"], {"PATH": "/usr/bin"}) == 0
    assert calls == [("/usr/bin/gh", ["/usr/bin/gh", "issue", "list"], {"PATH": "/usr/bin"})]


def test_gitcode_dispatch_does_not_resolve_gc_from_path(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda args, env: "gitcode")
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.shutil.which",
        lambda *args, **kwargs: pytest.fail("GitCode dispatch must not search PATH for gc"),
    )
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda executable, args, env: 0)
    assert dispatch(["issue", "list"], {"PATH": "/opt/homebrew/bin"}) == 0


@pytest.mark.parametrize("args", [["--version"], ["version"]])
def test_gitcode_proxy_version_is_explicit(monkeypatch, capsys, args):
    monkeypatch.setattr("gitcode_cli.gh_proxy.select_target", lambda argv, env: "gitcode")
    monkeypatch.setattr("gitcode_cli.gh_proxy.importlib.metadata.version", lambda package: "1.2.3")
    assert dispatch(args, {}) == 0
    output = capsys.readouterr().out
    assert "gh version 1.2.3 (pygitcode proxy)" in output
    assert "Target: GitCode" in output
    assert "not GitHub CLI" in output


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


def test_origin_host_routes_github_ssh_endpoint_to_native_gh(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "ssh://git@ssh.github.com:443/o/r.git\n", ""),
    )
    assert _origin_host() == "ssh.github.com"
    assert select_target([], {}) == "github"


def test_origin_host_ignores_git_failure(monkeypatch):
    from gitcode_cli.gh_proxy import _origin_host

    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "git")),
    )
    assert _origin_host() is None


@pytest.mark.parametrize(
    "args",
    [
        ["repo", "edit", "-d", "description", "gitcode.com/o/r"],
        ["repo", "edit", "--description", "github.com/other/repo", "gitcode.com/o/r"],
        ["repo", "edit", "--homepage", "https://github.com/o/r", "gitcode.com/o/r"],
        ["repo", "edit", "--description=description", "gitcode.com/o/r"],
        ["repo", "view", "--json", "url", "gitcode.com/o/r"],
        ["repo", "view", "-q", ".url", "-t", "{{.url}}", "gitcode.com/o/r"],
        ["repo", "fork", "--org", "organization", "gitcode.com/o/r"],
        ["repo", "view", "--", "gitcode.com/o/r"],
    ],
)
def test_repo_positional_routing_skips_option_values(args, monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "github.com")
    assert _positional_repo_host(args) == "gitcode.com"
    assert select_target(args, {}) == "gitcode"


@pytest.mark.parametrize(
    "args",
    [
        ["repo", "edit", "--homepage", "https://gitcode.com/o/r"],
        ["repo", "edit", "-d", "gitcode.com/o/r"],
        ["repo", "view", "--json", "url"],
        ["repo", "view", "--"],
    ],
)
def test_repo_option_value_never_selects_a_host(args):
    assert _positional_repo_host(args) is None


@pytest.mark.parametrize("origin", [None, "github.com"])
@pytest.mark.parametrize(
    "argv",
    [
        ["pr", "view", "-c", "https://gitcode.com/o/r/pull/1"],
        ["issue", "view", "-c", "https://gitcode.com/o/r/issues/1"],
        ["pr", "view", "-wc", "https://gitcode.com/o/r/pull/1"],
        ["pr", "edit", "-r", "reviewer", "https://gitcode.com/o/r/pull/1"],
        ["pr", "edit", "-rreviewer", "https://gitcode.com/o/r/pull/1"],
        ["pr", "view", "-c", "-R", "gitcode.com/o/r", "1"],
        ["pr", "view", "-wRgitcode.com/o/r", "1"],
        ["issue", "view", "--", "https://gitcode.com/o/r/issues/1"],
        ["--", "pr", "--", "view", "-c", "https://gitcode.com/o/r/pull/1"],
    ],
)
def test_gitcode_resource_options_dispatch_to_gc_without_rewriting(monkeypatch, argv, origin):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: origin)
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    assert dispatch(argv, {}) == 0
    assert calls[0][0:2] == (sys.executable, ["-m", "gitcode_cli.cli", *argv])


@pytest.mark.parametrize(
    "argv",
    [
        ["pr", "edit", "-r", "https://gitcode.com/o/r/pull/1", "12"],
        ["pr", "view", "-q", "https://gitcode.com/o/r/pull/1", "12"],
        ["issue", "edit", "--attach", "https://gitcode.com/o/r/issues/1", "12"],
        ["pr", "create", "--body", "--repo=gitcode.com/o/r"],
        ["pr", "view", "-c", "https://github.com/o/r/pull/1"],
        ["pr", "checks", "-i", "10", "https://github.com/o/r/pull/1", "--watch"],
        ["repo", "clone", "-u", "gitcode.com/o/r", "github.com/o/r"],
        ["pr", "view", "1"],
    ],
)
def test_native_or_no_target_arguments_stay_unchanged(monkeypatch, argv):
    # Real native git/gh are never executed in routing tests.
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    assert dispatch(argv, {}) == 0
    assert calls == [("/native/gh", argv, {})]


@pytest.mark.parametrize(
    ("argv", "guide"),
    [
        (["pr", "checks", "-i", "10", "https://gitcode.com/o/r/pull/1"], "use gc pr checks directly"),
        (["pr", "checks", "--", "https://gitcode.com/o/r/pull/1"], "use gc pr checks directly"),
        (["pr", "--", "checks", "https://gitcode.com/o/r/pull/1"], "use gc pr checks directly"),
        (["--", "api", "user?access_token=synthetic-marker"], "use gc api directly"),
        (["-R", "gitcode.com/o/r", "release", "view", "synthetic-marker"], "use gc release view directly"),
        (["issue", "lock", "-r", "synthetic-marker", "https://gitcode.com/o/r/issues/1"], "not supported"),
        (["pr", "diff", "--color", "synthetic-marker", "https://gitcode.com/o/r/pull/1"], "--color"),
        (["pr", "merge", "--auto", "https://gitcode.com/o/r/pull/1"], "--auto"),
        (["repo", "clone", "-u", "synthetic-marker", "gitcode.com/o/r"], "--upstream-remote-name"),
    ],
)
def test_gitcode_target_rejects_unsupported_routes_before_any_backend(monkeypatch, argv, guide):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: "gitcode.com" if argv[0] == "--" else None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("native gh must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("nothing may be dispatched"))
    with pytest.raises(ProxyError, match=guide) as exc:
        dispatch(argv, {})
    assert "synthetic-marker" not in str(exc.value)


def test_option_values_and_passthrough_are_not_blocked_flags():
    validate_gitcode_command(["pr", "merge", "--body", "--auto", "1"])
    validate_gitcode_command(["repo", "clone", "gitcode.com/o/r", "--", "--template=/tmp/git-template"])


@pytest.mark.parametrize(
    "argv",
    [
        ["pr", "view", "-c", "-R", "github.com/o/r", "https://gitcode.com/o/r/pull/1"],
        ["issue", "view", "-c", "https://gitcode.com/o/r/issues/1", "-Rgithub.com/o/r"],
    ],
)
def test_resource_and_repo_host_conflict_is_not_hidden_by_boolean_flag(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit conflict must win"))
    with pytest.raises(ProxyError, match="URL host conflicts with --repo"):
        select_target(argv, {})


@pytest.mark.parametrize(
    "argv",
    [
        ["api", "--hostname", "gitcode.com", "user"],
        ["api", "user", "--hostname=gitcode.com"],
        ["auth", "login", "--hostname", "gitcode.com", "--with-token"],
        ["auth", "status", "-h", "gitcode.com"],
        ["auth", "token", "-hGitCode.com."],
        ["auth", "refresh", "--hostname", "gitcode.com"],
    ],
)
def test_explicit_native_hostname_for_gitcode_must_not_reach_either_backend(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit host must win"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("github must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("no backend may execute"))
    with pytest.raises(ProxyError, match="refusing to fall back"):
        dispatch(argv, {})


@pytest.mark.parametrize(
    "argv",
    [
        ["api", "--hostname=enterprise.example", "user"],
        ["auth", "status", "-h", "github.com"],
        ["auth", "token", "--hostname", "github.com"],
    ],
)
def test_explicit_native_github_hostname_bypasses_gitcode_origin(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit host must win"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    assert dispatch(argv, {}) == 0
    assert calls == [("/native/gh", argv, {})]


@pytest.mark.parametrize(
    ("argv", "env"),
    [
        (["repo", "clone", "https://gitcode.com/o/r.git"], {"GC_GH_TARGET": "github"}),
        (["repo", "view", "gitcode.com/o/r", "--repo=github.com/a/b"], {}),
        (["api", "user", "--hostname", "gitcode.com"], {"GC_GH_TARGET": "github"}),
        (["api", "user", "--hostname", "github.com"], {"GC_GH_TARGET": "gitcode"}),
        (["pr", "view", "1", "-Rgithub.com/o/r"], {"GC_GH_TARGET": "gitcode"}),
        (["pr", "view", "1", "-Rgitcode.com/o/r", "-Rgithub.com/o/r"], {}),
        (["api", "--hostname=gitcode.com", "--hostname=github.com", "user"], {}),
    ],
)
def test_explicit_gitcode_github_provider_conflicts_stop_before_backend(monkeypatch, argv, env):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit conflict must win"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("github must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("no backend may execute"))
    with pytest.raises(ProxyError, match="conflict"):
        dispatch(argv, env)


@pytest.mark.parametrize(
    "argv",
    [
        ["api", "-f", "--hostname=gitcode.com", "user"],
        ["api", "user", "--", "--hostname=gitcode.com"],
        ["auth", "status", "--jq", "--hostname=gitcode.com"],
        ["pr", "view", "-c", "-Hgitcode.com", "1"],
    ],
)
def test_literal_and_unrelated_hostname_options_do_not_route(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    assert select_target(argv, {}) == "github"


@pytest.mark.parametrize("flag", ["-h", "--homepage"])
def test_repo_homepage_value_does_not_override_the_actual_gitcode_repository(monkeypatch, flag):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    args = ["repo", "edit", flag, "https://github.com/o/site", "https://gitcode.com/o/repo.with.dot.git"]
    assert select_target(args, {}) == "gitcode"
    if flag == "-h":
        with pytest.raises(ProxyError, match="Use --homepage"):
            validate_gitcode_command(args)
    else:
        validate_gitcode_command(args)


@pytest.mark.parametrize("command", ["edit", "create"])
def test_native_repo_homepage_short_option_remains_unchanged_without_gitcode_evidence(monkeypatch, command):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    argv = ["repo", command, "-h", "https://gitcode.com/o/homepage.repo", "github.com/o/work"]
    assert dispatch(argv, {}) == 0
    assert calls == [("/native/gh", argv, {})]


@pytest.mark.parametrize(
    "url",
    [
        "https://gitcode.com/o/a.b",
        "https://gitcode.com/o/a.b.git",
        "ssh://git@ssh.gitcode.com:443/o/a.b.git",
        "git@gitcode.com:o/a.b.git",
    ],
)
def test_dotted_gitcode_remote_routes_with_origin_and_explicit_positional(monkeypatch, url):
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, stdout=url + "\n"),
    )
    assert select_target(["pr", "list"], {}) == "gitcode"
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit URL must win"))
    assert select_target(["repo", "view", url], {}) == "gitcode"


@pytest.mark.parametrize("flag", ["-t", "--show-token"])
def test_auth_status_native_show_token_flag_cannot_mask_gitcode_hostname(monkeypatch, flag):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit host must win"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("github must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("no backend may execute"))
    with pytest.raises(ProxyError, match="show-token"):
        dispatch(["auth", "status", flag, "--hostname", "gitcode.com"], {})


def test_auth_status_native_show_token_short_option_and_gc_long_template_remain_distinct(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    native = ["auth", "status", "-t", "--hostname", "github.com"]
    assert dispatch(native, {}) == 0
    assert calls == [("/native/gh", native, {})]
    validate_gitcode_command(["auth", "status", "--template", "{{.state}}"])


@pytest.mark.parametrize(
    "argv",
    [
        ["pr", "view", "--future-option", "opaque", "https://gitcode.com/o/r/pull/4"],
        ["issue", "edit", "--future-option", "opaque", "https://gitcode.com/o/r/issues/4"],
        ["repo", "view", "--future-option", "opaque", "https://gitcode.com/o/repo.with.dot"],
    ],
)
def test_unknown_option_with_ambiguous_gitcode_selector_is_refused_without_dispatch(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("ambiguity must be handled first"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("github must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("no backend may execute"))
    with pytest.raises(ProxyError, match="unrecognized option makes the GitCode .* ambiguous") as exc:
        dispatch(argv, {})
    assert "opaque" not in str(exc.value) and "https://" not in str(exc.value)


@pytest.mark.parametrize(
    "argv",
    [
        ["pr", "view", "--future-option", "opaque", "https://github.com/o/r/pull/4"],
        ["issue", "edit", "--future-option", "opaque", "4"],
        ["repo", "view", "--future-option", "opaque", "https://github.com/o/repo.with.dot"],
    ],
)
def test_unknown_option_without_explicit_gitcode_evidence_does_not_preempt_native(monkeypatch, argv):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    assert dispatch(argv, {}) == 0
    assert calls == [("/native/gh", argv, {})]


@pytest.mark.parametrize(
    "url",
    [
        "https://gitcode.com/o/r/",
        "https://gitcode.com/o/r.git/",
        "ssh://git@ssh.gitcode.com:443/o/r.with.dot.git/",
        "git@gitcode.com:o/r.with.dot.git/",
    ],
)
def test_gitcode_remote_trailing_slash_stays_gitcode_in_positional_and_origin(monkeypatch, url):
    monkeypatch.setattr(
        "gitcode_cli.gh_proxy.subprocess.run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, stdout=url + "\n"),
    )
    assert select_target(["pr", "list"], {}) == "gitcode"
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit URL must win"))
    assert select_target(["repo", "clone", url], {}) == "gitcode"


@pytest.mark.parametrize(
    "env",
    [
        {"GH_HOST": "gitcode.com"},
        {"GH_HOST": "GitCode.com."},
        {"GH_REPO": "gitcode.com/o/r"},
        {"GH_REPO": "ssh.gitcode.com/o/r", "GC_GH_TARGET": "github"},
        {"GH_REPO": "gitcode.com/o/r", "GC_GH_TARGET": "gitcode"},
        {"GH_HOST": "git.other.example", "GC_GITCODE_HOSTS": "git.other.example"},
    ],
)
def test_exact_gitcode_host_in_native_env_requires_affirmative_gitcode_selection(monkeypatch, env):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("do not infer a different repository"))
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("github must not be selected"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("no backend may execute"))
    with pytest.raises(ProxyError, match="Use gc directly"):
        dispatch(["issue", "list"], env)


def test_explicit_gitcode_repo_selection_does_not_reinterpret_native_environment(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: pytest.fail("explicit -R must win"))
    assert select_target(
        ["issue", "list", "-R", "gitcode.com/exact/target"], {"GH_REPO": "gitcode.com/other/name"}
    ) == ("gitcode")


@pytest.mark.parametrize(
    "env",
    [
        {"GH_HOST": "github.com"},
        {"GH_REPO": "github.com/o/r"},
        {"GH_HOST": "gitcode.com.github.example"},
        {"GH_REPO": "enterprise.example/gitcode.com/r"},
    ],
)
def test_native_github_host_environment_passthrough_is_unchanged(monkeypatch, env):
    monkeypatch.setattr("gitcode_cli.gh_proxy._origin_host", lambda: None)
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: "/native/gh")
    calls = []
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *args: calls.append(args) or 0)
    argv = ["issue", "list"]
    assert dispatch(argv, env) == 0
    assert calls == [("/native/gh", argv, env)]
