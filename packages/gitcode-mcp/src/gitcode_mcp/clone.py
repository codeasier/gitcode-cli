"""Clone into the caller's coding environment, separate from remote MCP tools."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .config import ConfigurationError, Settings, repository_name


class CloneError(RuntimeError):
    """A safe, actionable error without captured Git output or credentials."""


def _git(args: list[str], env: dict[str, str], timeout: int, *, allow_missing: bool = False) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise CloneError("Git is not installed in this execution environment.") from None
    except subprocess.TimeoutExpired:
        raise CloneError(
            "Git timed out. Inspect the destination before retrying; no existing files were deleted."
        ) from None
    if completed.returncode and not (allow_missing and completed.returncode == 1):
        # Git can echo remote responses, credential-helper failures or expanded URLs.
        raise CloneError(
            "Git failed. Check the repository, ref, network and Git credentials in this environment. "
            "Captured output is withheld because it may contain credentials. Inspect any partial destination before retrying."
        )
    return completed.stdout.strip()


def clone_repository(
    repository: str,
    destination: str | Path,
    *,
    branch: str | None = None,
    depth: int | None = None,
    ssh: bool = False,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Clone with temporary credentials, then check out without the PAT in the environment."""
    repository = repository_name(repository)
    environment = dict(os.environ if env is None else env)
    settings = Settings.from_env(environment)
    if settings.allowed_repositories and repository not in settings.allowed_repositories:
        raise ConfigurationError("Repository is not in GITCODE_MCP_ALLOWED_REPOS.")
    if branch and (branch.startswith("-") or any(c in branch for c in "\r\n\x00")):
        raise ConfigurationError("Invalid branch name.")
    if depth is not None and not 1 <= depth <= 1_000_000:
        raise ConfigurationError("Depth must be between 1 and 1000000.")
    if not 1 <= timeout <= 3600:
        raise ConfigurationError("Timeout must be between 1 and 3600 seconds.")
    destination = Path(destination).expanduser()
    if destination.exists() or destination.is_symlink():
        raise CloneError(
            "Destination already exists. Choose a new directory; existing files are never overwritten."
        )
    destination = destination.resolve()
    if not destination.parent.is_dir():
        raise CloneError("Destination parent directory must already exist.")
    username = environment.get("GITCODE_USERNAME", "")
    use_pat = bool(settings.token and not ssh)
    if use_pat and not re.fullmatch(r"[A-Za-z0-9_.@-]+", username):
        raise ConfigurationError(
            "Set GITCODE_USERNAME to your GitCode login for temporary HTTPS PAT authentication, "
            "or use --ssh / an existing Git credential helper without GITCODE_TOKEN and GC_TOKEN."
        )
    if use_pat and os.name != "posix":
        raise ConfigurationError(
            "Temporary PAT authentication requires a POSIX shell; use SSH or a Git credential helper on this platform."
        )

    # Keep credentials out of checkout filters/hooks and any diagnostic Git tracing.
    for key in list(environment):
        if key in {
            "GITCODE_TOKEN",
            "GC_TOKEN",
            "GITCODE_MCP_HTTP_TOKEN",
            "GITCODE_CLONE_TOKEN",
            "GITCODE_CLONE_USERNAME",
            "GIT_CURL_VERBOSE",
        } or key.startswith("GIT_TRACE"):
            environment.pop(key, None)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    if branch:
        _git(["check-ref-format", "--branch", branch], environment, 10)

    url = f"git@gitcode.com:{repository}.git" if ssh else f"https://gitcode.com/{repository}.git"
    with tempfile.TemporaryDirectory(prefix="gitcode-clone-") as temporary:
        temporary_path = Path(temporary)
        hooks = temporary_path / "hooks"
        hooks.mkdir()
        template = temporary_path / "template"
        template.mkdir()
        options = [
            "-c",
            f"core.hooksPath={hooks}",
            "-c",
            f"init.templateDir={template}",
            "-c",
            "http.followRedirects=false",
        ]
        network_env = environment.copy()
        if use_pat:
            askpass = temporary_path / "askpass"
            askpass.write_text(
                f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -I -m gitcode_mcp.askpass "$@"\n',
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            network_env.update(
                {
                    "GIT_ASKPASS": str(askpass),
                    "GITCODE_CLONE_TOKEN": settings.token,
                    "GITCODE_CLONE_USERNAME": username,
                }
            )
            # Reset helpers so Git cannot persist this transient PAT after a successful clone.
            options.extend(["-c", "credential.helper="])
        args = [*options, "clone", "--quiet", "--no-checkout"]
        if branch:
            args.extend(["--branch", branch])
        if depth is not None:
            args.extend(["--depth", str(depth)])
        args.extend(["--", url, str(destination)])
        try:
            destination.mkdir(mode=0o700)
        except FileExistsError:
            raise CloneError(
                "Destination was created by another process; choose a new directory."
            ) from None
        _git(args, network_env, timeout)
        # No network credential environment during checkout. Git filters may execute local programs.
        head = _git(
            ["-C", str(destination), "rev-parse", "--verify", "--quiet", "HEAD"],
            environment,
            10,
            allow_missing=True,
        )
        if head:
            # A fresh clone owns this new directory. Populate it without detaching its branch.
            _git(
                [*options, "-C", str(destination), "reset", "--quiet", "--hard", "HEAD"],
                environment,
                timeout,
            )
    return {
        "repository": repository,
        "path": str(destination),
        "head_sha": head or None,
        "clone_url": url,
        "execution_scope": "local_process",
        "authentication": "temporary_pat" if use_pat else "existing_git_credentials",
        "note": "This directory exists only in the environment that ran gitcode-clone. No push credentials were saved by this helper.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clone GitCode into this execution environment")
    parser.add_argument("repository", help="owner/repo (no token or URL)")
    parser.add_argument("destination", help="new local directory")
    parser.add_argument("--branch", help="branch or tag to clone")
    parser.add_argument("--depth", type=int, help="shallow clone depth")
    parser.add_argument("--ssh", action="store_true", help="use existing SSH authentication")
    parser.add_argument("--timeout", type=int, default=300, help="Git operation timeout in seconds")
    args = parser.parse_args(argv)
    try:
        payload = clone_repository(
            args.repository,
            args.destination,
            branch=args.branch,
            depth=args.depth,
            ssh=args.ssh,
            timeout=args.timeout,
        )
    except (ConfigurationError, CloneError, OSError) as exc:
        message = (
            str(exc)
            if isinstance(exc, (ConfigurationError, CloneError))
            else "Cannot create the destination or temporary helper files."
        )
        print(message, file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
