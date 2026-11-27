from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .compat import CompatStatus, iter_entries
from .errors import RepoResolutionError
from .repo import parse_remote_url_with_host, parse_repo_with_host, parse_resource_url
from .repo_default import proxy_remote_urls

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


def _explicit_repos(argv: Sequence[str]) -> list[str]:
    command, tail, start = _command_parts(argv)
    # Global and subcommand -R options may both be present. Never take a
    # routing hint from something supplied as another option's value.
    return [
        value
        for options in (_arguments(argv[:start], _REPO_OPTIONS), _arguments(tail, _value_options(command)))
        for flag, value in options
        if flag in _REPO_OPTIONS and value is not None
    ]


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
_REPO_POSITIONAL_COMMANDS = {"view", "clone", "fork", "edit", "delete", "sync", "set-default"}


def _is_repo_selector(command: str) -> bool:
    return command.startswith("repo ") and command.partition(" ")[2] in _REPO_POSITIONAL_COMMANDS


def _repo_candidate_host(candidate: str) -> str | None:
    for parser in (parse_remote_url_with_host, parse_repo_with_host):
        try:
            host, _, _ = parser(candidate)
        except RepoResolutionError:
            continue
        return host if host else None
    return None


def _remote_host(url: str) -> str | None:
    if "://" in url:
        try:
            parsed = urlsplit(url)
            return parsed.hostname if parsed.scheme.lower() in {"https", "http", "ssh", "git"} else None
        except ValueError:
            return None
    # Only SCP-style URLs are meaningful here, never parse a local path as HOST/OWNER/REPO.
    if ":" in url and "::" not in url:
        try:
            return parse_remote_url_with_host(url)[0]
        except RepoResolutionError:
            pass
    return None


def _positional_repo_host(argv: Sequence[str], env: Mapping[str, str] | None = None) -> str | None:
    """Extract the repo positional, not a preceding option's value."""
    command, tail, _ = _command_parts(argv)
    if not _is_repo_selector(command):
        return None
    if command != "repo set-default":
        candidate = _first_positional(tail, _value_options(command))
        return _repo_candidate_host(candidate) if candidate is not None else None
    selectors = [value for flag, value in _arguments(tail, _value_options(command)) if not flag]
    if len(selectors) > 1:
        raise ProxyError("Ambiguous set-default selector; specify exactly one host-qualified repository.")
    candidate = next(iter(selectors), None)
    if candidate is None:
        return None
    if "/" not in candidate:
        try:
            declared, effective = proxy_remote_urls(candidate)
        except RepoResolutionError as exc:
            raise ProxyError(str(exc)) from exc
        hosts = _gitcode_hosts(os.environ if env is None else env)
        raw_host, actual_host = _remote_host(declared), _remote_host(effective)
        # Never send a GitCode selector to native gh, even if insteadOf
        # changes the provider (in either direction) or the pin ignores it.
        for host in (raw_host, actual_host):
            if host and _normalize_host(host) in hosts:
                return host
        if actual_host:
            return actual_host
        raise ProxyError("Cannot verify the named remote provider; use a host-qualified repository.")
    return _remote_host(candidate) or _repo_candidate_host(candidate)


def _reject_proxy_token_option(argv: Sequence[str]) -> None:
    # Only inspect global options. A command's positional or option value
    # spelling "--token" (e.g. a comment body) is not a credential override.
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--" or not arg.startswith("-"):
            return
        if arg == "--token" or arg.startswith("--token="):
            raise ProxyError("The gh proxy does not accept --token. Use gc directly with configured authentication.")
        index += 2 if arg in {"-R", "--repo"} else 1


def _explicit_repo_hosts(argv: Sequence[str]) -> list[str]:
    hosts = []
    for explicit in _explicit_repos(argv):
        if not explicit:
            continue
        try:
            host, _, _ = parse_repo_with_host(explicit)
        except RepoResolutionError as exc:
            raise ProxyError(str(exc)) from exc
        if host:
            hosts.append(host)
    return hosts


def _valid_option_host(value: str) -> bool:
    hostname, colon, port = value.partition(":")
    if colon and (not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535):
        return False
    hostname = hostname.removesuffix(".")
    label_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    return len(hostname) <= 253 and all(re.fullmatch(label_pattern, label) for label in hostname.split("."))


def _option_hosts(argv: Sequence[str]) -> list[str]:
    """Read native host selectors, strictly validating the auth login route."""
    command, tail, _ = _command_parts(argv)
    options = _HOST_SELECTOR_OPTIONS.get(command)
    if options is None:
        return []
    if command != "auth login":
        # Keep pre-existing native routing for commands that do not support
        # this selector on the GitCode backend.
        return [
            value
            for option, value in _arguments(tail, _value_options(command))
            if option in options and value and re.fullmatch(r"[A-Za-z0-9.][A-Za-z0-9.-]*(?::[0-9]+)?", value)
        ]
    hosts: list[str] = []
    for index, option, raw_value in _indexed_arguments(tail, _value_options(command)):
        if option not in options:
            continue
        value = raw_value
        # Native gh accepts an attached value with an optional equals sign.
        # Do not strip an equals sign from a separate token or long option.
        if option == "-h" and value is not None and value.startswith("=") and tail[index].endswith(value):
            value = value[1:]
        if not value or not _valid_option_host(value):
            raise ProxyError("Invalid or missing explicit hostname; neither backend was selected.")
        hosts.append(value)
    if len({host.lower() for host in hosts}) > 1:
        raise ProxyError("Explicit hostname options conflict; neither backend was selected.")
    return hosts


def _gitcode_in_native_environment(env: Mapping[str, str]) -> bool:
    gitcode_hosts = _gitcode_hosts(env)
    host = env.get("GH_HOST", "")
    parts = env.get("GH_REPO", "").split("/")
    repo_host = parts[0] if len(parts) == 3 else ""
    return any(value and value.strip().lower().rstrip(".") in gitcode_hosts for value in (host, repo_host))


def _refuse_incompatible_gitcode_environment(env: Mapping[str, str], providers: set[str], override: str | None) -> None:
    if _gitcode_in_native_environment(env) and (providers != {"gitcode"} or override == "github"):
        raise ProxyError(
            "GH_HOST or GH_REPO names GitCode, but these native gh settings are not translated by the proxy. "
            "Use gc directly with a qualified -R gitcode.com/OWNER/REPO where applicable; refusing to fall back."
        )


def select_target(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> str:
    _reject_proxy_token_option(argv)
    env = os.environ if environ is None else environ
    _reject_ambiguous_gitcode_selector(argv, env)
    resource_host = _resource_url_host(argv)
    positional_host = _positional_repo_host(argv, env)
    repo_hosts = _explicit_repo_hosts(argv)
    option_hosts = _option_hosts(argv)
    candidates = [*repo_hosts, *option_hosts]
    candidates.extend(host for host in (resource_host, positional_host) if host is not None)
    providers = {_target_for_host(host, env) for host in candidates}
    override = env.get("GC_GH_TARGET")
    if override:
        target = override.strip().lower()
        if target not in {"gitcode", "github"}:
            raise ProxyError("GC_GH_TARGET must be 'gitcode' or 'github'.")
        if providers - {target}:
            raise ProxyError("Explicit target host conflicts with GC_GH_TARGET; neither backend was selected.")
        _refuse_incompatible_gitcode_environment(env, providers, target)
        return target

    _refuse_incompatible_gitcode_environment(env, providers, None)
    if resource_host and repo_hosts and _normalize_host(resource_host) != _normalize_host(repo_hosts[-1]):
        raise ProxyError("Issue/PR URL host conflicts with --repo.")
    if len(providers) > 1:
        raise ProxyError("Explicit target hosts conflict across GitCode and GitHub; neither backend was selected.")
    if providers:
        return providers.pop()

    host = _origin_host()
    if host:
        return _target_for_host(host, env)
    return "github"


_REPO_OPTIONS = {"-R", "--repo"}
_AUTH_HOST_OPTIONS = {"-h", "--hostname"}
_HOST_SELECTOR_OPTIONS = {
    "api": {"--hostname"},
    **dict.fromkeys(
        ("auth login", "auth logout", "auth refresh", "auth setup-git", "auth status", "auth switch", "auth token"),
        _AUTH_HOST_OPTIONS,
    ),
}
_FORMAT_OPTIONS = {"--json", "-q", "--jq", "-t", "--template"}
_BODY_OPTIONS = {"-b", "--body", "-F", "--body-file"}
_COMMENT_OPTIONS = {"-c", "--comment"}
_EDIT_OPTIONS = {
    *_BODY_OPTIONS,
    "-t",
    "--title",
    "-a",
    "--add-assignee",
    "-l",
    "--add-label",
    "-m",
    "--milestone",
    "--remove-assignee",
    "--remove-label",
    "--add-project",
    "--remove-project",
    "--attach",
}
_ALIASES = {"ls": "list", "new": "create"}

# Commands with a resource selector as their first positional. Include
# known direct-only/native-only selectors so a GitCode URL still routes to
# the GitCode policy before deciding whether the command may be forwarded.
_RESOURCE_VALUE_OPTIONS = {
    "issue close": {*_COMMENT_OPTIONS, "--duplicate-of", "-r", "--reason"},
    "issue comment": _BODY_OPTIONS,
    "issue delete": set(),
    "issue develop": {"-b", "--base", "-n", "--name", "--branch-repo"},
    "issue edit": _EDIT_OPTIONS
    | {
        "--add-blocked-by",
        "--add-blocking",
        "--add-sub-issue",
        "--parent",
        "--remove-blocked-by",
        "--remove-blocking",
        "--remove-sub-issue",
        "--type",
    },
    "issue lock": {"-r", "--reason"},
    "issue pin": set(),
    "issue reopen": _COMMENT_OPTIONS,
    "issue transfer": set(),
    "issue unlock": set(),
    "issue unpin": set(),
    "issue view": _FORMAT_OPTIONS,
    "pr audit": _FORMAT_OPTIONS | {"-s", "--state", "-L", "--limit", "--th1", "--th2", "--minutes-keyword"},
    "pr checkout": {"-b", "--branch"},
    "pr checks": _FORMAT_OPTIONS | {"-i", "--interval", "--scan-limit"},
    "pr close": _COMMENT_OPTIONS,
    "pr comment": _BODY_OPTIONS
    | {"--discussion-id", "--path", "--position", "--line", "--side", "--commit-id", "--commit"},
    "pr diff": {"--color", "-e", "--exclude"},
    "pr edit": _EDIT_OPTIONS | {"-B", "--base", "-r", "--add-reviewer", "--remove-reviewer"},
    "pr lock": {"-r", "--reason"},
    "pr merge": _BODY_OPTIONS | {"-t", "--subject", "-A", "--author-email", "--match-head-commit"},
    "pr ready": set(),
    "pr reopen": _COMMENT_OPTIONS,
    "pr revert": _BODY_OPTIONS | {"-t", "--title"},
    "pr review": _BODY_OPTIONS,
    "pr unlock": set(),
    "pr update-branch": set(),
    "pr view": _FORMAT_OPTIONS,
}

# Option arities used when recognizing -R and positional repo selectors.
# Include native flags that the registry rejects after selecting GitCode: their
# values still must not be mistaken for a repository or resource selector.
_LIST_OPTIONS = _FORMAT_OPTIONS | {"-L", "--limit", "-s", "--state", "-S", "--search"}
_CREATE_OPTIONS = _BODY_OPTIONS | {
    "-t",
    "--title",
    "-a",
    "--assignee",
    "-l",
    "--label",
    "-m",
    "--milestone",
    "-p",
    "--project",
    "-T",
    "--template",
    "--recover",
    "--json",
    "-q",
    "--jq",
    "--attach",
}
_OTHER_VALUE_OPTIONS = {
    "api": {
        "--api-version",
        "-X",
        "--method",
        "-f",
        "--raw-field",
        "-F",
        "--field",
        "-H",
        "--header",
        "--input",
        "--hostname",
        "-q",
        "--jq",
        "-t",
        "--template",
        "--cache",
        "--preview",
    },
    # Native gh reserves -t for --show-token, not gc's template shorthand.
    "auth status": _FORMAT_OPTIONS - {"-t"},
    "auth login": {"-h", "--hostname", "-p", "--git-protocol", "-s", "--scopes"},
    "auth token": {"-h", "--hostname", "-u", "--user"},
    "auth switch": {"-h", "--hostname", "-u", "--user"},
    "auth logout": {"-h", "--hostname", "-u", "--user"},
    "discussion comment": _BODY_OPTIONS,
    "discussion create": _BODY_OPTIONS | {"-t", "--title", "-c", "--category"},
    "discussion edit": _BODY_OPTIONS | {"-t", "--title", "-c", "--category"},
    "issue create": _CREATE_OPTIONS,
    "issue list": _LIST_OPTIONS
    | {
        "-a",
        "--assignee",
        "-A",
        "--author",
        "-l",
        "--label",
        "-m",
        "--milestone",
        "--mention",
        "--app",
        "--type",
        "--parent",
    },
    "issue status": _FORMAT_OPTIONS,
    "label create": {"-c", "--color", "-d", "--description"},
    "label edit": {"-c", "--color", "-d", "--description", "-n", "--name"},
    "label list": _LIST_OPTIONS,
    "pr create": _CREATE_OPTIONS | {"-B", "--base", "-H", "--head", "-r", "--reviewer"},
    "pr list": _LIST_OPTIONS
    | {"-a", "--assignee", "-A", "--author", "-l", "--label", "-B", "--base", "-H", "--head", "--app"},
    "pr status": _FORMAT_OPTIONS,
    "release create": {"-t", "--title", "-n", "--notes", "-F", "--notes-file", "--target"},
    "release edit": {"-t", "--title", "-n", "--notes", "-F", "--notes-file", "--target"},
    "repo clone": {"-u", "--upstream-remote-name"},
    "repo create": {
        "-d",
        "--description",
        "-h",
        "--homepage",
        "-g",
        "--gitignore",
        "-l",
        "--license",
        "-s",
        "--source",
        "-r",
        "--remote",
        "-t",
        "--team",
        "-p",
        "--template",
    },
    "repo edit": {
        "-d",
        "--description",
        "-h",
        "--homepage",
        "--default-branch",
        "--visibility",
        "--add-topic",
        "--remove-topic",
        "--squash-merge-commit-message",
    },
    "repo fork": {"--remote-name", "--org", "--fork-name"},
    "repo list": _FORMAT_OPTIONS | {"-L", "--limit", "--visibility", "-l", "--language", "--topic"},
    "repo sync": {"-b", "--branch", "-s", "--source"},
    "repo view": _FORMAT_OPTIONS | {"-b", "--branch"},
}


def _value_options(command: str) -> set[str]:
    command_opts = _RESOURCE_VALUE_OPTIONS.get(command, _OTHER_VALUE_OPTIONS.get(command, set()))
    return _REPO_OPTIONS | command_opts | _HOST_SELECTOR_OPTIONS.get(command, set())


def _option_parts(arg: str, value_options: set[str]) -> Iterator[tuple[str, str | None]]:
    if arg.startswith("--"):
        name, eq, attached = arg.partition("=")
        yield name, attached if eq else None
        return
    # Support compact booleans and attached short values, e.g. -wc and -wRHOST/O/R.
    for offset, char in enumerate(arg[1:], 2):
        name = "-" + char
        if name in value_options:
            yield name, arg[offset:] or None
            return
        yield name, None


def _indexed_arguments(args: Sequence[str], value_options: set[str]) -> Iterator[tuple[int, str, str | None]]:
    """Yield each flag or positional with its original token index."""
    index = 0
    while index < len(args):
        start = index
        arg = args[index]
        index += 1
        if arg == "--":
            yield from ((position, "", args[position]) for position in range(index, len(args)))
            return
        if not arg.startswith("-") or arg == "-":
            yield start, "", arg
            continue
        for name, inline in _option_parts(arg, value_options):
            if name in value_options and inline is None and index < len(args):
                yield start, name, args[index]
                index += 1
            else:
                yield start, name, inline


def _arguments(args: Sequence[str], value_options: set[str]) -> Iterator[tuple[str, str | None]]:
    """Yield option names and values, or an empty name for a positional."""
    return ((flag, value) for _, flag, value in _indexed_arguments(args, value_options))


def _command_parts(argv: Sequence[str]) -> tuple[str, Sequence[str], int]:
    """Locate the group/subcommand without treating global -R values as commands."""
    index = 0
    while index < len(argv) and argv[index].startswith("-"):
        if argv[index] == "--":
            index += 1
            break
        index += 2 if argv[index] in _REPO_OPTIONS else 1
    if index >= len(argv):
        return "", (), len(argv)
    start = index
    group = argv[index]
    index += 1
    if group != "api" and index < len(argv) and argv[index] == "--":
        index += 1
    if group != "api" and index < len(argv) and not argv[index].startswith("-"):
        subcommand = _ALIASES.get(argv[index], argv[index])
        return f"{group} {subcommand}", argv[index + 1 :], start
    return group, argv[index:], start


def _first_positional(argv: Sequence[str], value_options: set[str]) -> str | None:
    return next((value for flag, value in _arguments(argv, value_options) if not flag), None)


def _resource_candidate_host(command: str, candidate: str) -> str | None:
    target = parse_resource_url(candidate, command.partition(" ")[0])
    return target[0] if target else None


def _resource_url_host(argv: Sequence[str]) -> str | None:
    command, tail, _ = _command_parts(argv)
    if command not in _RESOURCE_VALUE_OPTIONS:
        return None
    candidate = _first_positional(tail, _value_options(command))
    if candidate is None:
        return None
    try:
        return _resource_candidate_host(command, candidate)
    except RepoResolutionError as exc:
        raise ProxyError(str(exc)) from exc


def _reject_ambiguous_gitcode_selector(argv: Sequence[str], env: Mapping[str, str]) -> None:
    command, tail, _ = _command_parts(argv)
    is_repo = _is_repo_selector(command)
    if not is_repo and command not in _RESOURCE_VALUE_OPTIONS:
        return
    values = _value_options(command)
    known = values | {"-h", "--help"}
    known.update(
        flag
        for entry in iter_entries()
        if entry.command == command and entry.flag
        for flag in [*entry.flag.split("/"), *entry.aliases]
    )
    first = True
    uncertain = False
    for flag, value in _arguments(tail, values):
        if flag:
            if first and flag not in known and value is None:
                uncertain = True
            continue
        if first:
            first = False
            if not uncertain:
                return
            continue
        if value:
            try:
                host = _repo_candidate_host(value) if is_repo else _resource_candidate_host(command, value)
            except RepoResolutionError:
                continue
            if host and _target_for_host(host, env) == "gitcode":
                raise ProxyError(
                    "An unrecognized option makes the GitCode repository or resource ambiguous. "
                    "Put the repository or resource first, or use gc directly; refusing to fall back to GitHub."
                )


def validate_gitcode_command(argv: Sequence[str]) -> None:
    if not argv or argv[0] in {"--help", "-h", "--version", "version"}:
        return
    if argv[0] == "help":
        topics = argv[1:]
        # Dispatch appends --help. Never let a value-taking flag or "--"
        # consume it and turn help into an executable command.
        if len(topics) > 2 or any(not topic or topic.startswith("-") for topic in topics):
            raise ProxyError("Use gh help with a supported GitCode command topic only, without arguments or flags.")
        validate_gitcode_command(topics)
        return

    command, tail, _ = _command_parts(argv)
    if not command or command in {"auth", "issue", "pr", "repo"}:
        return
    entries = [entry for entry in iter_entries() if entry.command == command]
    entry = next((entry for entry in entries if entry.flag is None), None)
    if entry is None or entry.status is not CompatStatus.IMPLEMENTED:
        raise ProxyError("This gh command is not supported for GitCode; refusing to fall back to GitHub.")
    if not entry.proxy_allowed:
        raise ProxyError(
            f"This gh command is not enabled for GitCode; use gc {entry.command} directly. "
            "The proxy is refusing to fall back to GitHub."
        )
    blocked = {
        flag: flag_entry.flag
        for flag_entry in entries
        if flag_entry.flag and (not flag_entry.proxy_allowed or flag_entry.status is not CompatStatus.IMPLEMENTED)
        for flag in [*flag_entry.flag.split("/"), *flag_entry.aliases]
    }
    if command == "auth status":
        blocked["-t"] = "-t/--show-token"
    for flag, value in _arguments(tail, _value_options(command)):
        if command in {"repo create", "repo edit"} and flag == "-h" and value is not None:
            raise ProxyError("Use --homepage to set a GitCode homepage or --help for help; refusing to fall back.")
        if flag in blocked:
            raise ProxyError(
                f"The GitCode proxy does not support {blocked[flag]} for {entry.command}. "
                f"See gc {entry.command} --help; refusing to fall back to GitHub."
            )


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
        command, tail, _ = _command_parts(args)
        if command == "auth login":
            # Click treats the equals in a short value as literal input.
            # Translate only a real selector, never an operand or native gh's argv.
            start = len(args) - len(tail)
            for index, option, _ in _indexed_arguments(tail, _value_options(command)):
                if option == "-h" and tail[index].startswith("-h="):
                    args[start + index] = f"--hostname={tail[index][3:]}"
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
