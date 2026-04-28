from __future__ import annotations

import re
import subprocess
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from .services import PullRequestService


def prompt_if_missing(value: str | None, prompt_text: str, hide_input: bool = False) -> str:
    """If value is None or empty, use click.prompt interactively."""
    if not value:
        return click.prompt(prompt_text, hide_input=hide_input)
    return value


def get_current_git_branch() -> str | None:
    """Get current git branch name, return None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_default_git_branch() -> str | None:
    """Try to get remote default branch (e.g., origin/HEAD), return None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if branch.startswith("origin/"):
            return branch[len("origin/") :]
        return branch
    except subprocess.CalledProcessError:
        return None


def read_body_file(path: str) -> str:
    """Read body content from a file."""
    return Path(path).read_text(encoding="utf-8")


def open_in_browser(url: str) -> None:
    """Open URL in default browser."""
    webbrowser.open(url)


def safe_number(item: Any, fallback: int | str) -> int | str:
    if isinstance(item, dict):
        if "number" in item and item["number"] is not None:
            return item["number"]
        if "iid" in item and item["iid"] is not None:
            return item["iid"]
    return fallback


# --- Issue / PR identifier resolvers ---

ISSUE_URL_RE = re.compile(r"https?://[^/]+/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)")
PR_URL_RE = re.compile(r"https?://[^/]+/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls?/(?P<number>\d+)")


def parse_issue_url(url: str) -> tuple[str, str, str] | None:
    """Parse an issue URL into (owner, repo, number). Returns None if not a match."""
    match = ISSUE_URL_RE.match(url.strip())
    if match:
        return match.group("owner"), match.group("repo"), match.group("number")
    return None


def parse_pr_url(url: str) -> tuple[str, str, str] | None:
    """Parse a PR URL into (owner, repo, number). Returns None if not a match."""
    match = PR_URL_RE.match(url.strip())
    if match:
        return match.group("owner"), match.group("repo"), match.group("number")
    return None


def resolve_issue_arg(identifier: str):
    """Resolve an issue identifier (number or URL) into (owner, repo, number).

    Returns (None, None, number) if it's just a number, or (owner, repo, number) if a URL.
    """
    url_result = parse_issue_url(identifier)
    if url_result:
        return url_result
    return None, None, identifier


def resolve_pr_arg(identifier: str, owner: str, repo: str, service: PullRequestService) -> tuple[str, str, str]:
    """Resolve a PR identifier (number, URL, or branch) into (owner, repo, number).

    Returns (owner, repo, number). If branch is given, queries the API to find the PR.
    Raises click.ClickException if not found.
    """
    # Try URL first
    url_result = parse_pr_url(identifier)
    if url_result:
        return url_result

    # Try pure number
    if identifier.isdigit():
        return owner, repo, identifier

    # Treat as branch name — search open PRs with this head branch
    items = service.list(owner, repo, state="open", head=identifier)
    for item in items:
        head_ref = item.get("head", {}).get("ref", "")
        if head_ref == identifier:
            return owner, repo, str(item["number"])

    raise click.ClickException(f"No open pull request found for branch '{identifier}'.")
