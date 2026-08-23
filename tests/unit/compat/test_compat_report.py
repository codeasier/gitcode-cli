from __future__ import annotations

import json

from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.compat import (
    CompatStatus,
    iter_entries,
    render_markdown_report,
    statistics,
)


def test_statistics_groups_by_top_level_command() -> None:
    stats = statistics()
    assert set(stats.keys()) == {"auth", "issue", "pr", "repo"}
    for bucket in stats.values():
        # Only status_kind keys, e.g. "implemented_subcommand" or
        # "not_in_cli_flag" — both status and kind are separated by an underscore.
        valid_statuses = {s.value for s in CompatStatus}
        valid_kinds = {"subcommand", "flag"}
        for key, count in bucket.items():
            assert count > 0
            # Try the longest-status match first so "not_in_cli" wins over "not".
            status: str | None = None
            kind: str | None = None
            for candidate in sorted(valid_statuses, key=len, reverse=True):
                if key.startswith(candidate + "_"):
                    status = candidate
                    kind = key[len(candidate) + 1 :]
                    break
            assert status is not None and kind in valid_kinds, f"unparseable key {key!r}"


def test_statistics_total_matches_iter_entries() -> None:
    stats = statistics()
    total = sum(sum(bucket.values()) for bucket in stats.values())
    assert total == sum(1 for _ in iter_entries())


def test_render_markdown_report_includes_legend_and_sections() -> None:
    md = render_markdown_report()
    assert "Status legend" in md
    assert "## auth" in md
    assert "## issue" in md
    assert "## pr" in md
    assert "## repo" in md
    assert "Statistics" in md
    # Implementation status should dominate.
    assert "implemented" in md


def test_render_markdown_report_uses_real_flags() -> None:
    md = render_markdown_report()
    # Sanity: at least one of the well-known pending flags appears in the table.
    assert "| `auth status` | `--json` | pending |" in md
    assert "| `pr edit` | `-B/--base` | unsupported |" in md
    # And the unsupported marker key from the capabilities module.
    assert "PR_EDIT_BASE" in md or "base branch" in md


def test_iter_entries_filters_by_group() -> None:
    auth_entries = list(iter_entries(groups=["auth"]))
    issue_entries = list(iter_entries(groups=["issue"]))
    assert all(e.command.startswith("auth ") for e in auth_entries)
    assert all(e.command.startswith("issue ") for e in issue_entries)
    assert auth_entries and issue_entries


def test_iter_entries_filters_by_status() -> None:
    pending = list(iter_entries(statuses=[CompatStatus.PENDING]))
    assert pending
    assert all(e.status is CompatStatus.PENDING for e in pending)


def test_gc_compat_report_runs() -> None:
    result = CliRunner().invoke(main, ["compat", "report", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "gc ↔ gh compatibility matrix" in result.output


def test_gc_compat_stats_runs_as_json() -> None:
    result = CliRunner().invoke(main, ["compat", "stats"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload.keys()) == {"auth", "issue", "pr", "repo"}


def test_gc_compat_list_filters_pending() -> None:
    result = CliRunner().invoke(main, ["compat", "list", "--status", "pending"])
    assert result.exit_code == 0, result.output
    assert "pending" in result.output
    assert "unsupported" not in result.output.splitlines()[0]  # only pending rows
