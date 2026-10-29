"""Targeted PR label edits with identity-bound, non-destructive confirmation."""

from __future__ import annotations

from typing import Any

import click

from ..errors import GCError
from ..services import PullRequestService
from ._milestones import milestone_number


def _names(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise click.UsageError("PR label input must not contain control characters.")
    names = tuple(dict.fromkeys(part.strip() for part in value.split(",")))
    if any(not name or name in {".", ".."} for name in names):
        raise click.UsageError("PR labels require explicit nonempty names other than '.' or '..'.")
    return names


def _snapshot(item: Any, number: int) -> dict[str, int]:
    if not isinstance(item, dict) or milestone_number(item.get("number")) != number:
        raise ValueError("wrong PR number")
    if milestone_number(item.get("id")) is None or not isinstance(item.get("labels"), list):
        raise ValueError("missing PR identity or labels")
    labels: dict[str, int] = {}
    for label in item["labels"]:
        if not isinstance(label, dict):
            raise ValueError("malformed label")
        name, identity = label.get("name"), milestone_number(label.get("id"))
        if not isinstance(name, str) or not name or identity is None or name in labels:
            raise ValueError("ambiguous label identity")
        labels[name] = identity
    return labels


class PRLabelPlan:
    def __init__(self, service: PullRequestService, *, add: str | None, remove: str | None):
        self.service = service
        self.add, self.remove = _names(add), _names(remove)
        self.requested = bool(self.add or self.remove)
        if set(self.add) & set(self.remove):
            raise click.UsageError("Cannot add and remove the same PR label; no PR write was attempted.")

    @staticmethod
    def _error(number: int, *, partial: bool) -> click.ClickException:
        if partial:
            return click.ClickException(
                f"PR #{number} may have been updated, but its labels were not confirmed. "
                "Inspect the PR before retrying; no write was repeated or rolled back."
            )
        return click.ClickException(f"Unable to verify PR #{number} and its labels; no PR write was attempted.")

    def preflight(self, item: Any, number: int) -> None:
        try:
            _snapshot(item, number)
        except ValueError as exc:
            raise self._error(number, partial=False) from exc

    def read(self, owner: str, repo: str, number: int, *, partial: bool) -> dict[str, Any]:
        try:
            item = self.service.get(owner, repo, number)
            if not isinstance(item, dict):
                raise ValueError("missing PR object")
            _snapshot(item, number)
        except (GCError, ValueError) as exc:
            raise self._error(number, partial=partial) from exc
        return item

    def apply(self, owner: str, repo: str, number: int, before: dict[str, Any]) -> bool:
        """Apply only differences; callers confirm all edited fields on one final snapshot."""
        try:
            existing = _snapshot(before, number)
            additions = [name for name in self.add if name not in existing]
            removals = [name for name in self.remove if name in existing]
            if additions:
                self.service.add_labels(owner, repo, number, additions)
            for name in removals:
                self.service.remove_label(owner, repo, number, name)
        except (GCError, ValueError) as exc:
            raise self._error(number, partial=True) from exc
        return bool(additions or removals)

    def confirm(self, number: int, before: dict[str, Any], after: Any) -> dict[str, Any]:
        try:
            initial, actual = _snapshot(before, number), _snapshot(after, number)
            if milestone_number(before["id"]) != milestone_number(after["id"]):
                raise ValueError("PR identity changed")
            preserved = set(initial) - set(self.remove)
            if not (preserved | set(self.add)).issubset(actual) or set(self.remove) & set(actual):
                raise ValueError("unconfirmed label membership")
            if any(actual[name] != initial[name] for name in preserved):
                raise ValueError("label identity changed")
        except ValueError as exc:
            raise self._error(number, partial=True) from exc
        return after
