from __future__ import annotations

import re
import subprocess
from urllib.parse import unquote, urlsplit

from .errors import RepoResolutionError

_URL_HOST = r"(?P<host>\[[^\]]+\]|[^/:]+)"
HTTPS_RE = re.compile(rf"https?://(?:[^@/]+@)?{_URL_HOST}(?::\d+)?/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")
SSH_URL_RE = re.compile(rf"ssh://(?:[^@/]+@)?{_URL_HOST}(?::\d+)?/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")
SSH_RE = re.compile(r"(?:[^@/:]+@)?(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$")


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
    for pattern in (HTTPS_RE, SSH_URL_RE, SSH_RE):
        match = pattern.match(url.strip())
        if match:
            host = match.group("host")
            if host.startswith("[") and host.endswith("]"):
                host = host[1:-1]
            return host, match.group("owner"), match.group("repo")
    raise RepoResolutionError("Unsupported remote URL. Use a GitCode HTTPS or SSH repository URL.")


def validate_gitcode_repo(host: str | None, owner: str, name: str) -> tuple[str, str]:
    if host is not None and host.lower().rstrip(".") not in {"gitcode.com", "ssh.gitcode.com"}:
        raise RepoResolutionError("Repository host is not supported; gc works with gitcode.com repositories.")
    for segment in (owner, name):
        decoded = unquote(segment)
        if (
            not decoded
            or decoded in {".", ".."}
            or decoded.startswith("-")
            or any(char in decoded for char in "/\\?#%:@")
            or any(char.isspace() or ord(char) < 32 for char in decoded)
        ):
            raise RepoResolutionError("Invalid repository format. Owner and repository must be nonempty path segments.")
    return owner, name


def parse_resource_url(value: str, kind: str) -> tuple[str, str, str, str] | None:
    """Preserve the host until routing/validation; never downgrade a bad URL to a branch."""
    value = value.strip()
    if "://" not in value:
        return None
    try:
        url = urlsplit(value)
        endpoint = "issues" if kind == "issue" else "(?:pulls?|merge_requests)"
        match = re.fullmatch(rf"/([^/]+)/([^/]+)/{endpoint}/([0-9]+)/?", url.path)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.port not in {None, 443 if url.scheme == "https" else 80}
            or not match
        ):
            raise ValueError
    except ValueError:
        raise RepoResolutionError(f"Invalid {kind} URL.") from None
    return url.hostname, match.group(1), match.group(2), match.group(3)


def parse_remote_url(url: str) -> tuple[str, str]:
    _, owner, repo = parse_remote_url_with_host(url)
    return owner, repo


def resolve_repo(explicit_repo: str | None = None) -> tuple[str, str]:
    if explicit_repo:
        return validate_gitcode_repo(*parse_repo_with_host(explicit_repo))
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RepoResolutionError("Unable to infer repo from current directory. Use -R OWNER/REPO.") from exc
    return validate_gitcode_repo(*parse_remote_url_with_host(result.stdout.strip()))
