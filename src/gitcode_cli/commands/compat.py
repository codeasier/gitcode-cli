"""``gc compat`` subcommand — render the gh-compatibility matrix."""

from __future__ import annotations

import json
import sys

import click

from ..compat import CompatStatus, iter_entries, render_markdown_report, statistics
from ..helptext import set_gc_help
from ..utils import safe_echo


@click.group(
    "compat",
    short_help="Inspect gc ↔ gh compatibility status",
    help="Inspect the authoritative gh-compatibility registry used to track issue #68.",
)
def compat_group() -> None:
    pass


@compat_group.command(  # type: ignore[attr-defined]
    "report",
    short_help="Render the compatibility matrix",
    help=(
        "Render the compatibility matrix as Markdown. The output mirrors the "
        "structure of issue #68 and is regenerated from the registry on every "
        "run; do not edit it by hand."
    ),
)
@click.option("--stdout", "to_stdout", is_flag=True, help="Write Markdown to stdout instead of disk.")
def compat_report(to_stdout: bool) -> None:
    markdown = render_markdown_report()
    if to_stdout:
        safe_echo(markdown)
        return
    safe_echo(markdown)
    safe_echo(
        "\n(hint: re-run with --stdout to capture the report, e.g. `gc compat report --stdout > COMPATIBILITY.md`)",
        err=True,
    )


@compat_group.command(  # type: ignore[attr-defined]
    "stats",
    short_help="Print registry statistics as JSON",
    help=("Print aggregated status counts per top-level group as JSON on stdout."),
)
def compat_stats() -> None:
    json.dump(statistics(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


@compat_group.command(  # type: ignore[attr-defined]
    "list",
    short_help="List entries (one per line)",
    help=(
        "List all registry entries. By default only pending and unsupported "
        "entries are shown; pass --all to include everything."
    ),
)
@click.option("--all", "show_all", is_flag=True, help="Show every entry, not just open work.")
@click.option("--status", "status_filter", multiple=True, help="Filter by status (repeatable).")
def compat_list(show_all: bool, status_filter: tuple[str, ...]) -> None:
    statuses = tuple(CompatStatus(s) for s in status_filter) if status_filter else None
    if statuses is None and not show_all:
        statuses = (CompatStatus.PENDING, CompatStatus.UNSUPPORTED, CompatStatus.NOT_IN_CLI)
    for entry in iter_entries(statuses=statuses):
        safe_echo(f"{entry.command:<22} {entry.flag or '-':<28} {entry.status.value:<13} {entry.note}")


set_gc_help(
    compat_group,
    gc_usage="gc compat <command>",
    gc_command_sections=[
        ("COMMANDS", ["report", "stats", "list"]),
    ],
    gc_examples=[
        "gc compat report --stdout",
        "gc compat stats",
        "gc compat list --status pending",
    ],
    gc_arguments_help=[
        "The registry replaces the hand-maintained table in issue #68.",
    ],
)
