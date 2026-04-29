from __future__ import annotations

import subprocess
import sys

import click

from .utils import get_current_git_branch, get_default_git_branch, read_body_file


def get_body_from_options(body: str | None, body_file: str | None, editor: bool) -> str | None:
    """Resolve body text from inline text, file/stdin, or editor."""
    if body is not None and body_file:
        raise click.UsageError("cannot use --body and --body-file together")
    if body is not None:
        return body
    if body_file:
        if body_file == "-":
            return sys.stdin.read()
        return read_body_file(body_file)
    if editor:
        return click.edit()
    return None


def get_default_base_branch() -> str:
    """Return the detected default git branch for CLI base-branch inference."""
    branch = get_default_git_branch()
    if not branch:
        raise click.ClickException("Unable to determine the default base branch. Use --base.")
    return branch


def normalize_multi_values(values: tuple[str, ...] | None) -> str | None:
    """Normalize repeatable click option values for API calls."""
    if not values:
        return None
    return ",".join(values)


def resolve_pr_identifier_or_current_branch(identifier: str | None) -> str:
    """Return the given PR identifier or fall back to the current branch name."""
    if identifier is not None:
        return identifier
    branch = get_current_git_branch()
    if not branch:
        raise click.ClickException("Unable to detect current branch. Specify a PR or branch explicitly.")
    return branch


def get_fill_info(mode: str = "last") -> tuple[str, str]:
    """Get title and body from git commits on current branch.

    Args:
        mode: "last" (latest commit), "first" (first commit), or "verbose" (all commits)

    Returns:
        (title, body) tuple
    """
    base_branch = get_default_git_branch() or "main"
    current_branch = get_current_git_branch()
    if not current_branch:
        raise click.ClickException("Unable to detect current branch for --fill.")

    try:
        if mode == "last":
            result = subprocess.run(
                ["git", "log", "-1", "--format=%s%n%n%b", "--no-merges"],
                capture_output=True,
                text=True,
                check=True,
            )
        elif mode == "first":
            result = subprocess.run(
                ["git", "log", f"{base_branch}..{current_branch}", "--format=%s%n%n%b", "--no-merges", "--reverse"],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n\n", 1)
            result = subprocess.run(
                ["echo", lines[0] if lines else ""],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                ["git", "log", f"{base_branch}..{current_branch}", "--format=%s%n%n%b", "--no-merges"],
                capture_output=True,
                text=True,
                check=True,
            )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"Failed to get commit info: {exc}") from exc

    output = result.stdout.strip()
    if not output:
        return "", ""

    parts = output.split("\n\n", 1)
    title = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""

    if mode == "verbose" and body:
        lines = []
        commits = subprocess.run(
            ["git", "log", f"{base_branch}..{current_branch}", "--format=%s", "--no-merges"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in commits.stdout.strip().split("\n"):
            if line:
                lines.append(f"- {line}")
        body = "\n".join(lines)

    return title, body
