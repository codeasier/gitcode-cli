from __future__ import annotations

import sys

import click

from .utils import get_current_git_branch, get_default_git_branch, read_body_file


def get_body_from_options(body: str | None, body_file: str | None, editor: bool) -> str | None:
    """Resolve body text from inline text, file/stdin, or editor."""
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
