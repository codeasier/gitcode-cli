from __future__ import annotations

import re
import subprocess

from .errors import RepoResolutionError

HTTPS_RE = re.compile(r"https?://[^/]+/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")
SSH_RE = re.compile(r"git@[^:]+:(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")


def parse_repo(repo: str) -> tuple[str, str]:
    parts = repo.split("/")
    if len(parts) == 3:
        _, owner, name = parts
    elif len(parts) == 2:
        owner, name = parts
    else:
        raise RepoResolutionError("Invalid repo format. Use OWNER/REPO or HOST/OWNER/REPO.")
    return owner, name


def parse_remote_url(url: str) -> tuple[str, str]:
    for pattern in (HTTPS_RE, SSH_RE):
        match = pattern.match(url.strip())
        if match:
            return match.group("owner"), match.group("repo")
    raise RepoResolutionError(f"Unsupported remote URL: {url}")


def resolve_repo(explicit_repo: str | None = None) -> tuple[str, str]:
    if explicit_repo:
        return parse_repo(explicit_repo)
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RepoResolutionError("Unable to infer repo from current directory. Use -R OWNER/REPO.") from exc
    return parse_remote_url(result.stdout.strip())
