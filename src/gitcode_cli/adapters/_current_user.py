"""Resolve explicit @me aliases without guessing from display names."""

from __future__ import annotations

import click

from ..errors import GCError
from ..services import UserService


def resolve_me(users: UserService | None, *values: str | None) -> tuple[str | None, ...]:
    if "@me" not in values:
        return values
    if users is None:
        raise click.ClickException("failed to resolve @me: current user lookup is unavailable; no write was attempted")
    try:
        current = users.current()
    except (GCError, ValueError) as exc:
        raise click.ClickException("failed to resolve @me: current user lookup failed; no write was attempted") from exc
    login = current.get("login") if isinstance(current, dict) else None
    if (
        not isinstance(login, str)
        or not login
        or any(
            character.isspace() or character in ",/\\@?#:" or ord(character) < 32 or ord(character) == 127
            for character in login
        )
    ):
        raise click.ClickException("failed to resolve @me: current user has no valid login; no write was attempted")
    return tuple(login if value == "@me" else value for value in values)
