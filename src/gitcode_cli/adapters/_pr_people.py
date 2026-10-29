"""Verified GitCode PR role changes, separate from generic PR create/update."""

from __future__ import annotations

from typing import Any

import click

from ..errors import GCError
from ..services import PullRequestService, UserService
from ._milestones import milestone_number


def _login(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character.isspace() or character in ",/\\@?#:" or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise click.ClickException("PR people must be nonempty account logins, not names, teams or URLs.")
    return value


def resolve_people(values: tuple[str, ...], users: UserService | None) -> tuple[str, ...]:
    logins = []
    current = None
    for value in values:
        for part in value.split(","):
            login = part.strip()
            if login == "@me":
                if users is None:
                    raise click.ClickException("Current-user lookup is unavailable; no PR write was attempted.")
                if current is None:
                    current = users.current()
                login = current.get("login") if isinstance(current, dict) else None
            logins.append(_login(login))
    return tuple(dict.fromkeys(logins))


def _members(item: dict[str, Any], field: str) -> dict[str, str]:
    values = item.get(field)
    if not isinstance(values, list):
        raise ValueError("missing role collection")
    members = {}
    for user in values:
        if not isinstance(user, dict):
            raise ValueError("malformed role member")
        login = _login(user.get("login"))
        identity = user.get("id")
        if isinstance(identity, bool) or not isinstance(identity, (str, int)) or not str(identity).strip():
            raise ValueError("missing role member identity")
        if login in members:
            raise ValueError("duplicate role member")
        members[login] = str(identity)
    return members


class PRPeoplePlan:
    def __init__(
        self,
        service: PullRequestService,
        users: UserService | None,
        *,
        assignees: tuple[str, ...] = (),
        reviewers: tuple[str, ...] = (),
        remove_assignees: tuple[str, ...] = (),
        remove_reviewers: tuple[str, ...] = (),
    ):
        self.service = service
        self.add = {
            "assignees": resolve_people(assignees, users),
            "approval_reviewers": resolve_people(reviewers, users),
        }
        self.remove = {
            "assignees": resolve_people(remove_assignees, users),
            "approval_reviewers": resolve_people(remove_reviewers, users),
        }
        self.fields = tuple(field for field in self.add if self.add[field] or self.remove[field])
        for field in self.fields:
            if set(self.add[field]) & set(self.remove[field]):
                raise click.UsageError(
                    "Cannot add and remove the same account in one PR role; no PR write was attempted."
                )

    def _error(self, number: int, *, partial: bool) -> click.ClickException:
        if partial:
            return click.ClickException(
                f"PR #{number} may have been created or updated, but its people changes were not confirmed. "
                "Inspect the PR before retrying; no write was repeated."
            )
        return click.ClickException(f"Unable to verify PR #{number} and its people; no PR write was attempted.")

    def read(self, owner: str, repo: str, number: int, *, partial: bool) -> dict[str, Any]:
        try:
            item = self.service.get(owner, repo, number)
            if not isinstance(item, dict) or milestone_number(item.get("number")) != number:
                raise ValueError("wrong PR number")
            if milestone_number(item.get("id")) is None:
                raise ValueError("missing PR identity")
            for field in self.fields:
                _members(item, field)
        except (GCError, ValueError, click.ClickException) as exc:
            raise self._error(number, partial=partial) from exc
        return item

    def apply(
        self, owner: str, repo: str, number: int, before: dict[str, Any], *, force_read: bool = False
    ) -> dict[str, Any]:
        operations = {
            "assignees": (self.service.add_assignees, self.service.remove_assignees),
            "approval_reviewers": (self.service.add_reviewers, self.service.remove_reviewers),
        }
        wrote = False
        try:
            for field in self.fields:
                current = _members(before, field)
                additions = [login for login in self.add[field] if login not in current]
                removals = [login for login in self.remove[field] if login in current]
                add, remove = operations[field]
                if additions:
                    wrote = True
                    add(owner, repo, number, ",".join(additions))
                if removals:
                    wrote = True
                    remove(owner, repo, number, ",".join(removals))
            after = self.read(owner, repo, number, partial=True) if wrote or force_read else before
            if milestone_number(after.get("id")) != milestone_number(before.get("id")):
                raise ValueError("PR identity changed")
            for field in self.fields:
                initial, actual = _members(before, field), _members(after, field)
                preserved = set(initial) - set(self.remove[field])
                expected = preserved | set(self.add[field])
                if not expected.issubset(actual) or set(self.remove[field]) & set(actual):
                    raise ValueError("unconfirmed role membership")
                if any(actual[login] != initial[login] for login in preserved):
                    raise ValueError("role member identity changed")
        except (GCError, ValueError, click.ClickException) as exc:
            raise self._error(number, partial=True) from exc
        return after
