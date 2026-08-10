from __future__ import annotations

import re
import subprocess

from .errors import RepoResolutionError

HTTPS_RE = re.compile(r"https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")
SSH_RE = re.compile(r"git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")


def parse_repo_with_host(repo: str) -> tuple[str | None, str, str]:
    parts = repo.split("/")
    if len(parts) == 3:
        host, owner, name = parts
        return host, owner, name
    if len(parts) == 2:
        owner, name = parts
        return None, owner, name
    raise RepoResolutionError("Invalid repo format. Use OWNER/REPO or HOST/OWNER/REPO.")


def parse_repo(repo: str) -> tuple[str, str]:
    _, owner, name = parse_repo_with_host(repo)
    return owner, name


def parse_remote_url_with_host(url: str) -> tuple[str, str, str]:
    for pattern in (HTTPS_RE, SSH_RE):
        match = pattern.match(url.strip())
        if match:
            return match.group("host"), match.group("owner"), match.group("repo")
    raise RepoResolutionError(f"Unsupported remote URL: {url}")


def parse_remote_url(url: str) -> tuple[str, str]:
    _, owner, repo = parse_remote_url_with_host(url)
    return owner, repo


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
