"""At most one readback for a successful create's requested JSON output."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click

from ..errors import GCError
from ..json_projection import json_number

COMMON_FIELDS = {
    "author": ("author", "user", "creator"),
    "assignees": ("assignees",),
    "body": ("body", "description"),
    "createdAt": ("createdAt", "created_at"),
    "labels": ("labels",),
    "milestone": ("milestone",),
    "number": ("number",),
    "state": ("state",),
    "title": ("title",),
    "updatedAt": ("updatedAt", "updated_at"),
    "url": ("html_url", "web_url", "url"),
}
PR_FIELDS = {
    **COMMON_FIELDS,
    "base": ("base", "baseRefName", "target_branch"),
    "baseRefName": ("base", "baseRefName", "target_branch"),
    "baseRefOid": ("base", "baseRefOid"),
    "head": ("head", "headRefName", "source_branch"),
    "headRefName": ("head", "headRefName", "source_branch"),
    "headRefOid": ("head", "headRefOid"),
    "draft": ("draft", "work_in_progress"),
    "mergedAt": ("mergedAt", "merged_at"),
}


def _field_missing(field: str, aliases: tuple[str, ...], item: dict, result: dict) -> bool:
    if not any(alias in item for alias in aliases):
        return True
    # A present but invalid/API-only value is not a usable canonical field.
    return result.get(field) is None and any(item.get(alias) is not None for alias in aliases)


def created_output(
    item: Any,
    *,
    kind: str,
    json_fields: str | None,
    jq_query: str | None,
    project: Callable[[dict], dict],
    read: Callable[[int], Any],
    readback_done: bool = False,
    requested_milestone: bool = False,
) -> Any:
    if json_fields is None and not jq_query:
        return item
    unknown = f"{kind} creation may have succeeded, but its response cannot identify the result. "
    unknown += "Inspect the repository before retrying; no create request was repeated."
    if not isinstance(item, dict):
        raise click.ClickException(unknown)
    result = project(item)
    if readback_done:
        return result
    fields = PR_FIELDS if kind == "PR" else COMMON_FIELDS
    selected = set(fields) if jq_query else {value.strip() for value in (json_fields or "").split(",")}
    missing = any(_field_missing(field, fields[field], item, result) for field in selected.intersection(fields))
    missing_milestone = requested_milestone and "milestone" in selected and item.get("milestone") is None
    if not missing and not missing_milestone:
        return result
    number = json_number(item.get("number"))
    if number is None or number <= 0:
        raise click.ClickException(unknown)
    message = f"{kind} creation returned #{number}, but its requested output could not be read. "
    message += "Inspect it before retrying; no create request was repeated."
    try:
        snapshot = read(number)
    except (GCError, ValueError) as exc:
        raise click.ClickException(message) from exc
    if not isinstance(snapshot, dict) or json_number(snapshot.get("number")) != number:
        raise click.ClickException(message)
    return project(snapshot)
