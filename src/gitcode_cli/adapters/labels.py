"""Safe, additive repository-label copying; never replace the destination catalog."""

from __future__ import annotations

import re
from typing import Any

from ..errors import APIError, GCError
from ..services.labels import LabelService, validate_name


def _catalog(svc: LabelService) -> dict[str, dict]:
    index = {}
    for row in svc.list(limit=None):
        name = validate_name(row["name"])
        key = name.casefold()
        if key in index:
            raise APIError("Ambiguous case-equivalent names in label catalog.")
        index[key] = row
    return index


def _rgb(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#?(?:[a-fA-F0-9]{3}|[a-fA-F0-9]{6})", value):
        raise APIError("GitCode label did not provide a valid color.")
    value = value.lstrip("#").upper()
    return "#" + ("".join(c * 2 for c in value) if len(value) == 3 else value)


def upsert_label(service: LabelService, name: str, requested_color: str | None, default_color: str) -> str:
    existing = _catalog(service).get(name.casefold())
    if existing is None:
        service.create(name, requested_color or default_color)
        return "Created"
    if requested_color is None or _rgb(existing.get("color")) == requested_color:
        return "Kept"
    service.edit(existing["name"], None, requested_color)
    return "Updated"


def clone_labels(source: LabelService, destination: LabelService, *, force: bool) -> tuple[int, int, int]:
    # Inspect all pages and build/validate the entire plan before the first write.
    # Use name rather than numeric IDs, which belong to the source repository.
    originals = _catalog(source)
    existing = _catalog(destination)
    plan = []
    kept = 0
    for key, row in originals.items():
        current = existing.get(key)
        if current is not None and not force:
            kept += 1
            continue
        rgb = _rgb(row.get("color"))
        if current is not None and _rgb(current.get("color")) == rgb:
            kept += 1
            continue
        plan.append((current["name"] if current else row["name"], rgb, current is None))

    created = updated = 0
    for name, color, is_new in plan:
        try:
            if is_new:
                destination.create(name, color)
                created += 1
            else:
                destination.edit(name, None, color)
                updated += 1
        except GCError as exc:
            raise APIError(
                f"Label copy stopped at {name!r} after {created} confirmed creates and {updated} confirmed updates: "
                f"{exc}. Verify destination state before resuming."
            ) from None
    return created, updated, kept
