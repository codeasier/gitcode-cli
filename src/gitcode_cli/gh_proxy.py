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
from .repo import parse_remote_url_with_host, parse_repo_with_host

GITCODE_HOSTS_ENV = "GC_GITCODE_HOSTS"


class ProxyError(Exception):
    pass


def _normalize_host(host: str) -> str:
    host = host.strip().lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if ":" in host:
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
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"-R", "--repo"} and index + 1 < len(argv):
            repo = argv[index + 1]
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


def select_target(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    override = env.get("GC_GH_TARGET")
    if override:
        target = override.strip().lower()
        if target not in {"gitcode", "github"}:
            raise ProxyError("GC_GH_TARGET must be 'gitcode' or 'github'.")
        return target

    explicit = _explicit_repo(argv)
    if explicit:
        try:
            host, _, _ = parse_repo_with_host(explicit)
        except RepoResolutionError as exc:
            raise ProxyError(str(exc)) from exc
        if host:
            return _target_for_host(host, env)

    host = _origin_host()
    if host:
        return _target_for_host(host, env)
    return "github"


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
    if not argv or argv[0] in {"--help", "-h", "--version", "version"}:
        return

    tokens = _command_tokens(argv)
    if not tokens:
        return
    if len(tokens) == 1 and tokens[0] in {"auth", "issue", "pr"}:
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
