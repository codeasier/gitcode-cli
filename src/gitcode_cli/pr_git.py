"""Git actions bound to the PR's source repository and observed commit."""

from __future__ import annotations

import re
import secrets
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


def _git_source(source: PRHead, command: str, refspec: str, *options: str) -> None:
    """Refuse URL rewrites, then pin this invocation to the verified source.

    Git applies insteadOf once per configured URL; an explicit pushurl also
    disables pushInsteadOf. A fresh exact alias therefore expands to the
    canonical URL without subsequently rewriting that URL. Configuration is
    command-scoped: native credential helpers remain available, but no remote
    or configuration is saved. The second configuration prevents a rewrite
    added after the check from changing this operation's destination.
    """
    remote = "gc-pr-" + secrets.token_hex(16)
    occupied = _git("config", "--name-only", "--get-regexp", rf"^remote\.{remote}\.", check=False)
    if occupied.returncode != 1:
        raise GCError("Unable to reserve a private Git remote; branch operation refused.")
    configured = ("-c", f"remote.{remote}.url={source.url}")
    # get-url requires a repository-persisted remote in Git 2.56, so it
    # rejects command-scoped remotes. The no-network verbose listing expands
    # the same URL rules and also includes command-scoped configuration.
    direction = "push" if command == "push" else "fetch"
    marker = f" ({direction})"
    effective = _git(*configured, "remote", "-v")
    urls = [line for line in effective.stdout.splitlines() if line.startswith(f"{remote}\t") and line.endswith(marker)]
    if urls != [f"{remote}\t{source.url}{marker}"]:
        # The rewritten URL can contain credentials. Never include it in errors.
        raise GCError("Git URL rewriting changes the verified PR source; branch operation refused.")
    alias = remote + ":"
    pinned = (
        "-c",
        f"remote.{remote}.url={alias}",
        "-c",
        f"remote.{remote}.pushurl={alias}",
        "-c",
        f"url.{source.url}.insteadOf={alias}",
    )
    _git(*pinned, command, *options, "--", remote, refspec)


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
    _git_source(source, "push", f":{ref}", f"--force-with-lease={ref}:{source.sha}")
    return source.branch


def _remote_matches(source: PRHead, remote: str) -> bool:
    urls = _git("remote", "get-url", "--all", "--", remote).stdout.splitlines()
    if len(urls) != 1:
        return False
    if urls[0] == source.url:
        return True
    try:
        owner, repo = validate_gitcode_repo(*parse_remote_url_with_host(source.url))
    except RepoResolutionError:
        return False
    # Compare canonical spellings, not merely a parser which discards ports or
    # userinfo. An alternate service on the same hostname is not proven to be
    # the same repository. Git helpers/custom ports fail closed here.
    return urls[0] in {
        f"{prefix}{owner}/{repo}{suffix}"
        for prefix in (
            "https://gitcode.com/",
            "git@gitcode.com:",
            "ssh://git@gitcode.com/",
            "git@ssh.gitcode.com:",
            "ssh://git@ssh.gitcode.com/",
        )
        for suffix in ("", ".git")
    }


def _matches_upstream(source: PRHead, ref: str) -> bool:
    tracking = _git("for-each-ref", "--format=%(upstream:remotename)%00%(upstream:remoteref)", ref).stdout.strip()
    parts = tracking.split("\0")
    if len(parts) != 2 or parts[0] in ("", ".") or parts[1] != f"refs/heads/{source.branch}":
        return False
    return _remote_matches(source, parts[0])


def _verified_tracking_ref(source: PRHead) -> str | None:
    candidates = []
    for remote in _git("remote").stdout.splitlines():
        if not _remote_matches(source, remote):
            continue
        mapping = _git("config", "--get-all", f"remote.{remote}.fetch", check=False)
        if mapping.returncode or mapping.stdout.splitlines() != [f"+refs/heads/*:refs/remotes/{remote}/*"]:
            continue
        candidates.append(f"refs/remotes/{remote}/{source.branch}")
    if len(candidates) != 1:
        return None
    ref = candidates[0]
    if _git("show-ref", "--verify", "--quiet", ref, check=False).returncode:
        # A PR branch may have appeared since clone. Create only a missing
        # tracking ref; never overwrite a concurrent fetch's existing value.
        _git("update-ref", ref, source.sha, "0" * 40)
    return ref


def checkout_head(item: object, branch: str | None, *, detach: bool = False, force: bool = False) -> str:
    source = resolve_head(item)
    local = branch or source.branch
    _check_branch(local)
    _git_source(source, "fetch", f"refs/heads/{source.branch}", "--no-tags")
    fetched = _git("rev-parse", "--verify", "FETCH_HEAD^{commit}").stdout.strip()
    if fetched.lower() != source.sha:
        raise GCError("PR branch changed during fetch. Refresh the PR before retrying checkout.")
    if detach:
        _git("checkout", "--detach", source.sha, "--")
        return local
    ref = f"refs/heads/{local}"
    existing = _git("rev-parse", "--verify", ref, check=False)
    if existing.returncode == 0:
        if force and not _matches_upstream(source, ref):
            raise GCError(f"Branch '{local}' does not track the verified PR source branch; force checkout refused.")
        if not force and existing.stdout.strip().lower() != source.sha:
            raise GCError(f"Branch '{local}' already exists at another commit. Use --branch with a new name.")
        _git("checkout", local, "--")
        if force:
            _git("reset", "--hard", source.sha, "--")
    else:
        tracking_ref = _verified_tracking_ref(source)
        # Use the immutable object ID, not FETCH_HEAD or a tracking ref which
        # another concurrent fetch can overwrite.
        _git("checkout", "-b", local, source.sha, "--")
        if tracking_ref:
            _git("branch", f"--set-upstream-to={tracking_ref}", "--", local)
    return local
