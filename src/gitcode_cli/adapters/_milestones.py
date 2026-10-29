"""Read-only, unambiguous PR milestone input resolution."""

from __future__ import annotations

from typing import Any

import click

from ..services import IssueService


def milestone_number(value: Any) -> int | None:
    if type(value) is int:
        return value if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        try:
            number = int(value)
        except ValueError:
            return None
        return number if number > 0 else None
    return None


def _matching_numbers(items: Any, seen: set[int], title: str) -> list[int]:
    if not isinstance(items, list):
        raise click.ClickException("Milestone title lookup returned an invalid list; no PR write was attempted.")
    matches = []
    for item in items:
        number = milestone_number(item.get("number")) if isinstance(item, dict) else None
        if number is None or not isinstance(item.get("title"), str) or number in seen:
            raise click.ClickException("Milestone title lookup is incomplete or repeated; no PR write was attempted.")
        seen.add(number)
        if item["title"] == title:
            matches.append(number)
    return matches


def resolve_pr_milestone(service: IssueService | None, owner: str, repo: str, value: str | None) -> int | None:
    if value is None:
        return None
    title = value.strip()
    if not title:
        raise click.UsageError("Milestone must be a nonempty title or positive number.")
    if title.isascii() and title.isdigit():
        number = milestone_number(title)
        if number is None:
            raise click.UsageError("Milestone number must be positive; zero is not a verified clearing operation.")
        return number
    if service is None:
        raise click.ClickException("Milestone title lookup is unavailable; provide a positive milestone number.")

    matches: list[int] = []
    seen: set[int] = set()
    for page in range(1, 101):
        items = service.list_milestones(owner, repo, state="all", page=page, per_page=100)
        matches.extend(_matching_numbers(items, seen, title))
        if len(items) < 100:
            break
    else:
        raise click.ClickException("Milestone pagination limit exceeded; no PR write was attempted.")
    if len(matches) != 1:
        reason = "matched multiple milestones" if matches else "was not found"
        raise click.ClickException(f"Milestone title {reason}; no PR write was attempted.")
    return matches[0]
