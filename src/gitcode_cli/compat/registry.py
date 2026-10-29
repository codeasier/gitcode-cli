"""Authoritative registry of ``gc`` gh-compatibility status.

This module is the single source of truth for the ``gc`` ↔ ``gh`` compatibility
matrix that previously lived in GitCode issue #68. Tracking the matrix in the
issue body drifted every time a flag was implemented, marked unsupported, or
reclassified; CI now enforces that the registry, the Click command tree, and the
runtime guards stay in lockstep.

Status taxonomy
---------------
* ``implemented``  — Click option exists, behaviour matches ``gh`` semantics
  (or a clearly documented approximation).
* ``pending``      — Click option exists; invoking it raises a
  ``_pending_gh_compat("<pending_key>")`` ClickException. The optional
  ``pending_key`` field is the literal string passed to that helper.
* ``unsupported``  — Click option exists; invoking it raises
  ``unsupported("<unsupported_key>")``. The key must be present in
  ``adapters.capabilities.CAPABILITY_MESSAGES``.
* ``not_in_cli``   — ``gh`` exposes the flag but ``gc`` does not. Invoking it
  surfaces a Click "no such option" error.

Entries with ``flag is None`` describe a subcommand (e.g. ``issue lock``); the
status applies to the subcommand as a whole.

Adding or reclassifying an entry
--------------------------------
Edit this file in the same PR that changes the corresponding command code. The
``tests/unit/compat/test_registry_consistency.py`` suite enforces that every
``pending`` entry has a matching runtime guard, every ``unsupported`` entry has a
matching capability message, every ``implemented``/``pending``/``unsupported``
flag is actually registered with Click, and every ``not_in_cli`` flag is
absent.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Final

from ._types import CompatEntry, CompatStatus
from .entries import ENTRIES

# A tuple of ``CompatEntry`` keyed by ``(command, flag)``. ``flag is None``
# represents a subcommand-level entry. The tuple is the registry; do not mutate.
_ENTRIES: Final[tuple[CompatEntry, ...]] = tuple(ENTRIES)


def iter_entries(
    *,
    groups: Iterable[str] | None = None,
    statuses: Iterable[CompatStatus] | None = None,
) -> Iterator[CompatEntry]:
    """Iterate entries, optionally filtered by top-level group and/or status."""
    group_set = set(groups) if groups is not None else None
    status_set = set(statuses) if statuses is not None else None
    for entry in _ENTRIES:
        if group_set is not None:
            top = entry.command.split(" ", 1)[0]
            if top not in group_set:
                continue
        if status_set is not None and entry.status not in status_set:
            continue
        yield entry


def statistics() -> dict[str, dict[str, int]]:
    """Aggregate counts per top-level command group, row kind, and status.

    Returns ``{group: {status_label: count, ...}, ...}``. ``group`` is one of
    ``auth``/``issue``/``pr``. Subcommand rows (``flag is None``) are counted
    separately from flag rows so the totals match the structure of issue #68.
    """

    counts: dict[str, dict[str, int]] = {}
    for entry in _ENTRIES:
        top = entry.command.split(" ", 1)[0]
        bucket = counts.setdefault(top, {})
        key = f"{entry.status.value}_{'subcommand' if entry.flag is None else 'flag'}"
        bucket[key] = bucket.get(key, 0) + 1
    return counts


def render_markdown_report() -> str:
    """Render the registry as Markdown mirroring the issue #68 layout."""
    lines: list[str] = [
        "# gc ↔ gh compatibility matrix",
        "",
        "Auto-generated from `gitcode_cli.compat.registry`. Do not edit by hand; "
        "edit `src/gitcode_cli/compat/entries.py` and run `gc compat report`.",
        "",
        "## Status legend",
        "",
        "| Status | Meaning |",
        "|---|---|",
        "| **implemented**  | CLI placeholder + behaviour implemented |",
        "| **pending**      | CLI placeholder + flag parses but raises `_pending_gh_compat()` |",
        "| **unsupported**  | CLI placeholder + adapter marks it unsupported (GitCode API limit) |",
        "| **not_in_cli**   | `gh` baseline exposes it but `gc` does not |",
        "",
    ]
    for group in ("auth", "issue", "pr", "repo"):
        sub_entries = [e for e in iter_entries(groups=[group]) if e.flag is None]
        flag_entries = [e for e in iter_entries(groups=[group]) if e.flag is not None]
        if not sub_entries and not flag_entries:
            continue
        lines.append(f"## {group}")
        lines.append("")
        lines.append("### Subcommands")
        lines.append("")
        lines.append("| Subcommand | Status | Notes |")
        lines.append("|---|---|---|")
        for entry in sub_entries:
            note = entry.note.replace("|", "\\|")
            lines.append(f"| `{entry.command}` | {entry.status.value} | {note} |")
        lines.append("")
        lines.append("### Flags")
        lines.append("")
        lines.append("| Command | Flag | Status | Notes |")
        lines.append("|---|---|---|---|")
        for entry in flag_entries:
            note = entry.note.replace("|", "\\|")
            lines.append(f"| `{entry.command}` | `{entry.flag}` | {entry.status.value} | {note} |")
        lines.append("")

    lines.append("## Statistics")
    lines.append("")
    lines.append("| Group | implemented | pending | unsupported | not_in_cli | Total |")
    lines.append("|---|---|---|---|---|---|")
    grand = {"implemented": 0, "pending": 0, "unsupported": 0, "not_in_cli": 0}
    for group in ("auth", "issue", "pr", "repo"):
        bucket = statistics().get(group, {})
        impl = bucket.get("implemented", 0)
        pend = bucket.get("pending", 0)
        unsup = bucket.get("unsupported", 0)
        ninc = bucket.get("not_in_cli", 0)
        total = impl + pend + unsup + ninc
        lines.append(f"| {group} | {impl} | {pend} | {unsup} | {ninc} | {total} |")
        for k, v in (("implemented", impl), ("pending", pend), ("unsupported", unsup), ("not_in_cli", ninc)):
            grand[k] += v
    gtotal = sum(grand.values())
    lines.append(
        f"| **Total** | **{grand['implemented']}** | **{grand['pending']}** | "
        f"**{grand['unsupported']}** | **{grand['not_in_cli']}** | **{gtotal}** |"
    )
    lines.append("")
    return "\n".join(lines)
