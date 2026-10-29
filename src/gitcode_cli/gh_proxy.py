from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from . import __version__
from .compat import CompatStatus, iter_entries
from .errors import RepoResolutionError
from .repo import parse_remote_url_with_host, parse_repo_with_host, parse_resource_url

GITCODE_HOSTS_ENV = "GC_GITCODE_HOSTS"


class ProxyError(Exception):
    pass


def _normalize_host(host: str) -> str:
    host = host.strip().lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.rstrip(".")


def _gitcode_hosts(environ: Mapping[str, str]) -> set[str]:
    configured = environ.get(GITCODE_HOSTS_ENV, "")
    return {
        "gitcode.com",
        "ssh.gitcode.com",
        *(_normalize_host(host) for host in configured.split(",") if host.strip()),
    }


def _target_for_host(host: str, environ: Mapping[str, str]) -> str:
    return "gitcode" if _normalize_host(host) in _gitcode_hosts(environ) else "github"


def _explicit_repo(argv: Sequence[str]) -> str | None:
    repo: str | None = None
    tokens = _command_tokens(argv)
    if tokens and tokens[0] in _RESOURCE_COMMANDS:
        value_options = _resource_value_options(tokens[0], tokens[1] if len(tokens) > 1 else "")
    else:
        value_options = _REPO_VALUE_OPTIONS
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            break
        if arg in {"-R", "--repo"} and index + 1 < len(argv):
            repo = argv[index + 1]
            index += 2
            continue
        if arg in value_options - {"-R", "--repo"}:
            index += 2
            continue
        if arg.startswith("--repo="):
            repo = arg.partition("=")[2]
        elif arg.startswith("-R") and len(arg) > 2:
            repo = arg[2:]
        index += 1
    return repo


def _origin_host() -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        host, _, _ = parse_remote_url_with_host(result.stdout.strip())
        return host
    except (OSError, subprocess.CalledProcessError, RepoResolutionError):
        return None


# Repo subcommands whose first positional argument names a repository
# ([HOST/]OWNER/REPO or a full URL). `repo rename <new-name>` and
# `repo list <owner>` are deliberately excluded: their positionals do not
# carry host information.
_REPO_POSITIONAL_COMMANDS = {"view", "clone", "fork", "edit", "delete", "sync"}


# Values of these options must never become a repository routing hint.
_REPO_VALUE_OPTIONS = {
    "-R",
    "--repo",
    "--json",
    "-q",
    "--jq",
    "-t",
    "--template",
    "--org",
    "--fork-name",
    "-d",
    "--description",
    "--homepage",
    "--default-branch",
    "--visibility",
}


def _positional_repo_host(argv: Sequence[str]) -> str | None:
    """Extract the repo positional, not a preceding option's value."""
    tokens = _command_tokens(argv)
    if len(tokens) < 2 or tokens[0] != "repo" or tokens[1] not in _REPO_POSITIONAL_COMMANDS:
        return None
    # Global -R options have already been accounted for by select_target.
    # Starting after the subcommand preserves option/argument boundaries.
    index = list(argv).index(tokens[1], list(argv).index("repo") + 1) + 1
    while index < len(argv):
        candidate = argv[index]
        if candidate == "--":
            index += 1
            if index == len(argv):
                return None
            candidate = argv[index]
            break
        if candidate in _REPO_VALUE_OPTIONS:
            index += 2
            continue
        if candidate.startswith("-"):
            index += 1
            continue
        break
    else:
        return None
    for parser in (parse_remote_url_with_host, parse_repo_with_host):
        try:
            host, _, _ = parser(candidate)
        except RepoResolutionError:
            continue
        return host if host else None
    return None


def select_target(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    resource_host = _resource_url_host(argv)
    override = env.get("GC_GH_TARGET")
    if override:
        target = override.strip().lower()
        if target not in {"gitcode", "github"}:
            raise ProxyError("GC_GH_TARGET must be 'gitcode' or 'github'.")
        if resource_host and target != _target_for_host(resource_host, env):
            raise ProxyError("Issue/PR URL conflicts with GC_GH_TARGET.")
        return target

    explicit = _explicit_repo(argv)
    if explicit:
        try:
            host, _, _ = parse_repo_with_host(explicit)
        except RepoResolutionError as exc:
            raise ProxyError(str(exc)) from exc
        if host:
            if resource_host and _normalize_host(host) != _normalize_host(resource_host):
                raise ProxyError("Issue/PR URL host conflicts with --repo.")
            return _target_for_host(host, env)

    if resource_host:
        return _target_for_host(resource_host, env)
    positional_host = _positional_repo_host(argv)
    if positional_host:
        return _target_for_host(positional_host, env)

    host = _origin_host()
    if host:
        return _target_for_host(host, env)
    return "github"


_RESOURCE_COMMANDS = {
    "issue": {"view", "close", "reopen", "edit", "comment", "delete", "develop"},
    "pr": {"view", "close", "reopen", "edit", "comment", "merge", "review", "checkout", "diff", "ready", "audit"},
}
_RESOURCE_VALUE_OPTIONS = {
    "-R",
    "--repo",
    "--json",
    "-q",
    "--jq",
    "-t",
    "--template",
    "--title",
    "--subject",
    "-b",
    "--body",
    "-F",
    "--body-file",
    "-c",
    "--comment",
    "--branch",
    "--base",
    "--name",
    "-n",
    "--reason",
    "--duplicate-of",
    "--add-assignee",
    "--remove-assignee",
    "--add-label",
    "--remove-label",
    "--add-reviewer",
    "--remove-reviewer",
    "--milestone",
    "-a",
    "-l",
    "--author-email",
    "-A",
    "--discussion-id",
    "--path",
    "--position",
    "--line",
    "--side",
    "--commit-id",
    "--commit",
    "--state",
    "--limit",
    "-L",
    "--th1",
    "--th2",
    "--minutes-keyword",
}


def _resource_value_options(group: str, command: str) -> set[str]:
    options = set(_RESOURCE_VALUE_OPTIONS)
    if group == "issue" and command == "close":
        options.add("-r")
    if command == "edit":
        options.add("-m")
    if command == "audit":
        options.add("-s")
    if group == "pr" and command == "review":
        options -= {"-a", "-c", "--comment"}
    return options


def _resource_url_host(argv: Sequence[str]) -> str | None:
    tokens = _command_tokens(argv)
    if len(tokens) < 2 or tokens[1] not in _RESOURCE_COMMANDS.get(tokens[0], set()):
        return None
    group, command = tokens[:2]
    index = list(argv).index(command, list(argv).index(group) + 1) + 1
    value_options = _resource_value_options(group, command)
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            index += 1
            break
        if arg in value_options:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            break
    if index >= len(argv):
        return None
    try:
        target = parse_resource_url(argv[index], group)
    except RepoResolutionError as exc:
        raise ProxyError(str(exc)) from exc
    return target[0] if target else None


def _command_tokens(argv: Sequence[str]) -> list[str]:
    tokens: list[str] = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-R", "--repo"}:
            skip_next = True
            continue
        if arg.startswith("--repo=") or (arg.startswith("-R") and len(arg) > 2):
            continue
        if not arg.startswith("-"):
            tokens.append(arg)
    return tokens


def validate_gitcode_command(argv: Sequence[str]) -> None:
    if not argv or argv[0] in {"--help", "-h", "--version", "help", "version"}:
        return

    tokens = _command_tokens(argv)
    if not tokens:
        return
    if len(tokens) == 1 and tokens[0] in {"auth", "issue", "pr", "repo"}:
        return

    aliases = {"ls": "list", "new": "create"}
    command = " ".join([tokens[0], aliases.get(tokens[1], tokens[1])]) if len(tokens) >= 2 else tokens[0]
    supported = {
        entry.command for entry in iter_entries() if entry.flag is None and entry.status is not CompatStatus.NOT_IN_CLI
    }
    if command not in supported:
        raise ProxyError(f"gh command '{command}' is not supported for GitCode; refusing to fall back to GitHub.")


def _same_file(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return False


def find_real_gh(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    shim = env.get("GC_GH_SHIM")
    override = env.get("GC_REAL_GH")
    if override:
        candidate = shutil.which(override) if not Path(override).is_absolute() else override
        if not candidate or not Path(candidate).is_file() or not os.access(candidate, os.X_OK):
            raise ProxyError(f"GC_REAL_GH does not point to an executable: {override}")
        if shim and _same_file(candidate, shim):
            raise ProxyError("GC_REAL_GH points to the gh proxy itself.")
        return str(Path(candidate).resolve())

    shim_dir = str(Path(shim).resolve().parent) if shim else None
    path_entries = [
        entry
        for entry in env.get("PATH", os.defpath).split(os.pathsep)
        if not shim_dir or not _same_file(entry or os.curdir, shim_dir)
    ]
    candidate = shutil.which("gh", path=os.pathsep.join(path_entries))
    if not candidate or (shim and _same_file(candidate, shim)):
        raise ProxyError("Unable to find the native GitHub CLI. Set GC_REAL_GH to its executable path.")
    return str(Path(candidate).resolve())


def _exec(executable: str, args: list[str], environ: Mapping[str, str]) -> int:
    child_env = dict(environ)
    if os.name == "nt":
        return subprocess.call([executable, *args], env=child_env)
    os.execve(executable, [executable, *args], child_env)
    return 0  # pragma: no cover


def _print_gitcode_proxy_version() -> None:
    try:
        version = importlib.metadata.version("pygitcode")
    except importlib.metadata.PackageNotFoundError:
        version = __version__

    print(f"gh version {version} (pygitcode proxy)")
    print("Target: GitCode (gitcode.com)")
    print("Backend: gc (GitCode CLI), not GitHub CLI")
    print("https://github.com/codeasier/gitcode-cli")


def dispatch(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if environ is None else environ
    if select_target(args, env) == "gitcode":
        validate_gitcode_command(args)
        if args in (["--version"], ["version"]):
            _print_gitcode_proxy_version()
            return 0
        if args and args[0] == "help":
            args = [*args[1:], "--help"]
        child_env = dict(env)
        child_env["GC_GH_PROXY_ACTIVE"] = "1"
        child_env["GC_GH_PROXY_TARGET"] = "gitcode"
        return _exec(sys.executable, ["-m", "gitcode_cli.cli", *args], child_env)

    return _exec(find_real_gh(env), args, env)


def main() -> None:
    try:
        raise SystemExit(dispatch())
    except ProxyError as exc:
        print(f"gh proxy error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
