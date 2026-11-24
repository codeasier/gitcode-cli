"""A GitCode-only default pinned to an existing local Git fetch remote."""

from __future__ import annotations

import os
import re
from subprocess import CompletedProcess, SubprocessError, run

from .errors import RepoResolutionError

_KEY = "gc.default-repository"
_CONFIG = ("config", "--local", "--no-includes")
_REMOTE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}")
_SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}")
_FETCH_PREFIX = re.compile(
    r"(?:https://gitcode\.com/|git@(?:ssh\.)?gitcode\.com:|"
    r"ssh://git@(?:gitcode\.com(?::22)?|ssh\.gitcode\.com(?::443)?)/)",
    re.IGNORECASE | re.ASCII,
)
_AUTH_ENV = {"GC_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}
_STALE = (
    "The configured GitCode default repository no longer matches one supported Git fetch remote. "
    "Run gc repo set-default again, use --unset, or specify -R OWNER/REPO."
)
_INFER = "Unable to infer repo from current directory. Use -R OWNER/REPO."


def _git(*args: str) -> CompletedProcess[str]:
    # These commands inspect or edit local config only. Do not pass CLI
    # credentials or permit Git tracing to disclose config values.
    env = {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in _AUTH_ENV and not name.upper().startswith("GIT_TRACE")
    }
    try:
        return run(["git", *args], capture_output=True, encoding="utf-8", env=env, timeout=10, check=False)
    except (OSError, SubprocessError, UnicodeError):
        raise RepoResolutionError("Unable to read or update the local Git configuration.") from None


def _parse_target(path: str) -> tuple[str, str] | None:
    owner, sep, repo = path.partition("/")
    if sep and _SLUG.fullmatch(owner) and _SLUG.fullmatch(repo):
        return owner, repo
    return None


def _fetch_target(url: str) -> tuple[str, str] | None:
    # Only documented canonical spelling families; reject userinfo, alternate
    # ports, encoded separators, query/fragment, helpers, and local paths.
    prefix = _FETCH_PREFIX.match(url)
    if prefix:
        return _parse_target(url[prefix.end() :].removesuffix("/").removesuffix(".git"))
    return None


def _config_rows(*query: str, scopes: tuple[str, ...] = _CONFIG) -> list[str]:
    result = _git(*scopes, "--null", *query)
    if result.returncode == 1 and not result.stdout and not result.stderr:
        return []
    if result.returncode != 0:
        raise RepoResolutionError(_INFER)
    if not result.stdout.endswith("\0"):
        raise RepoResolutionError("Could not read the local Git configuration safely.")
    return result.stdout[:-1].split("\0")


def _fetch_rows() -> dict[str, list[str]]:
    remotes: dict[str, list[str]] = {}
    for row in _config_rows("--get-regexp", r"^remote\..*\.url$"):
        key, sep, value = row.partition("\n")
        if not sep:
            raise RepoResolutionError("Could not read the local Git remote configuration safely.")
        remote = key[len("remote.") : -len(".url")]
        if _REMOTE_NAME.fullmatch(remote):
            remotes.setdefault(remote, []).append(value)
    return remotes


def _remote_rows(remote: str) -> list[str]:
    return _config_rows("--get-all", f"remote.{remote}.url")


def _verified_target(remote: str, urls: list[str], error: str) -> tuple[str, str]:
    target = _fetch_target(urls[0]) if len(urls) == 1 else None
    if target is None:
        raise RepoResolutionError(error)
    effective = _git("remote", "get-url", "--all", "--", remote)
    if effective.returncode or effective.stdout != urls[0] + "\n":
        raise RepoResolutionError(error)
    return target


def _stored_target() -> tuple[str, str] | None:
    rows = _config_rows("--get-all", _KEY)
    if not rows:
        return None
    remote, sep, path = rows[0].partition("\t")
    expected = _parse_target(path)
    if len(rows) != 1 or not sep or not _REMOTE_NAME.fullmatch(remote) or expected is None:
        raise RepoResolutionError(_STALE)
    if _verified_target(remote, _remote_rows(remote), _STALE) != expected:
        raise RepoResolutionError(_STALE)
    return expected


def proxy_remote_urls(remote: str) -> tuple[str, str]:
    """Read both declared and effective fetch identities for a native-gh selector.

    Unlike our pin, native Git sees includes, worktree, global and command
    scopes. Never echo either URL (it could contain credentials).
    """
    error = "Cannot verify a unique fetch destination for the named remote; use a host-qualified repository."
    rows = _config_rows("--get-all", f"remote.{remote}.url", scopes=("config", "--includes"))
    if len(rows) != 1:
        raise RepoResolutionError(error)
    result = _git("remote", "get-url", "--all", "--", remote)
    lines = result.stdout.splitlines()
    if result.returncode or len(lines) != 1 or not lines[0]:
        raise RepoResolutionError(error)
    return rows[0], lines[0]


def configured_target() -> tuple[str, str] | None:
    # Never feed this setting into provider selection or into a gh-dispatched
    # request. Both proxy branches keep their existing repository resolution.
    if os.environ.get("GC_GH_PROXY_ACTIVE") == "1":
        return None
    return _stored_target()


def view_default() -> tuple[str, str] | None:
    return _stored_target()


def set_default(selector: str) -> tuple[str, str]:
    if _REMOTE_NAME.fullmatch(selector):
        remote = selector
    else:
        parts = selector.split("/")
        if len(parts) == 3 and parts[0].lower() in {"gitcode.com", "ssh.gitcode.com"}:
            parts = parts[1:]
        identity = _parse_target("/".join(parts))
        if identity is None:
            raise RepoResolutionError("Use a local GitCode remote name or [gitcode.com/]OWNER/REPO.")
        matches = [name for name, urls in _fetch_rows().items() if any(_fetch_target(url) == identity for url in urls)]
        if len(matches) != 1:
            raise RepoResolutionError("Expected exactly one matching GitCode fetch remote. Select a remote by name.")
        remote = matches[0]
    target = _verified_target(
        remote, _remote_rows(remote), "Expected a single supported GitCode fetch URL without Git URL rewriting."
    )
    result = _git(*_CONFIG, "--replace-all", _KEY, f"{remote}\t{'/'.join(target)}")
    if result.returncode:
        raise RepoResolutionError("Unable to save the default in the local Git configuration.")
    return target


def unset_default() -> None:
    result = _git(*_CONFIG, "--unset-all", _KEY)
    if result.returncode not in (0, 5):
        raise RepoResolutionError("Unable to remove the default from the local Git configuration.")
