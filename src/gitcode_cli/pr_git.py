"""Git actions bound to the PR's source repository and observed commit."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .errors import GCError, RepoResolutionError
from .repo import parse_remote_url_with_host, parse_repo_with_host, validate_gitcode_repo


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=check)
    except (OSError, subprocess.CalledProcessError):
        # Git errors can contain credentials from remote config or a helper.
        raise GCError("Git operation failed. Verify the repository/branch state before retrying.") from None


def _check_branch(branch: str) -> None:
    if (
        not branch
        or branch == "HEAD"
        or branch.startswith("-")
        or any(ord(char) < 32 for char in branch)
        or _git("check-ref-format", f"refs/heads/{branch}", check=False).returncode
    ):
        raise GCError("Invalid PR branch name.")


@dataclass(frozen=True)
class PRHead:
    url: str
    branch: str
    sha: str


def _source_identity(source: object) -> tuple[str, str]:
    if not isinstance(source, dict):
        raise GCError("Unable to verify PR source repository; branch operation refused.")
    identities = []
    if isinstance(source.get("full_name"), str):
        identities.append(validate_gitcode_repo(*parse_repo_with_host(source["full_name"])))
    # Cross-check any advertised repository identity, but never execute an API-
    # supplied clone command/URL or use the current origin's same-named branch.
    for field in ("html_url", "clone_url", "ssh_url"):
        if source.get(field):
            if not isinstance(source[field], str):
                raise RepoResolutionError("Invalid PR source repository identity.")
            identity = validate_gitcode_repo(*parse_remote_url_with_host(source[field]))
            identities.append(identity)
    if not identities:
        raise GCError("Unable to verify PR source repository; branch operation refused.")
    if any(identity != identities[0] for identity in identities):
        raise RepoResolutionError("PR source repository identities disagree.")
    return identities[0]


def resolve_head(item: object) -> PRHead:
    head = item.get("head") if isinstance(item, dict) else None
    source = head.get("repo") if isinstance(head, dict) else None
    owner, repo = _source_identity(source)
    assert isinstance(head, dict)
    branch, sha = head.get("ref"), head.get("sha")
    if not isinstance(branch, str) or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise GCError("Unable to verify PR branch and full head SHA; branch operation refused.")
    _check_branch(branch)
    return PRHead(f"https://gitcode.com/{owner}/{repo}.git", branch, sha.lower())


def delete_head(item: object) -> str:
    source = resolve_head(item)
    assert isinstance(item, dict)
    base = item.get("base") if isinstance(item.get("base"), dict) else {}
    repo = item["head"]["repo"]
    # Be conservative when the source/base repositories cannot be compared.
    if source.branch in (repo.get("default_branch"), base.get("ref")):
        raise GCError("Refusing to delete the repository's default or PR base branch.")
    ref = f"refs/heads/{source.branch}"
    # The explicit lease is checked by the server at deletion time. A prior
    # ls-remote alone would leave a race with another push.
    _git("push", f"--force-with-lease={ref}:{source.sha}", "--", source.url, f":{ref}")
    return source.branch


def checkout_head(item: object, branch: str | None) -> str:
    source = resolve_head(item)
    local = branch or source.branch
    _check_branch(local)
    _git("fetch", "--no-tags", "--", source.url, f"refs/heads/{source.branch}")
    fetched = _git("rev-parse", "--verify", "FETCH_HEAD^{commit}").stdout.strip()
    if fetched.lower() != source.sha:
        raise GCError("PR branch changed during fetch. Refresh the PR before retrying checkout.")
    ref = f"refs/heads/{local}"
    existing = _git("rev-parse", "--verify", ref, check=False)
    if existing.returncode == 0:
        if existing.stdout.strip().lower() != source.sha:
            raise GCError(f"Branch '{local}' already exists at another commit. Use --branch with a new name.")
        _git("checkout", local, "--")
    else:
        # Use the immutable object ID, not FETCH_HEAD or a tracking ref which
        # another concurrent fetch can overwrite.
        _git("checkout", "-b", local, source.sha, "--")
    return local
