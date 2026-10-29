"""Exact displayed surface against gh 2.89.0, with reasoned platform differences."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .surface import assert_surface, expected_surface, parse_help

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gh-cli-compat"
BASELINE = json.loads((FIXTURES / "command_baseline.json").read_text(encoding="utf-8"))
COVERAGE = json.loads((FIXTURES / "coverage.json").read_text(encoding="utf-8"))["help_surface"]
pytestmark = [pytest.mark.e2e, pytest.mark.compat]


def _node(command: str) -> dict:
    node = BASELINE["root"]
    for part in command.split():
        node = next(child for child in node["subcommands"] if child["path"][-1] == part)
    return node


def test_manifest_covers_exact_selected_scope():
    assert COVERAGE["schema_version"] == 1
    assert COVERAGE["baseline_version"] == BASELINE["version"] == "2.89.0"
    assert set(COVERAGE["commands"]) == {"", "issue", "issue create", "pr", "pr create"}
    assert COVERAGE["gc_invariant_basis"] == "The pinned gh snapshot does not record usage or aliases."
    for command, policy in COVERAGE["commands"].items():
        expected_surface(_node(command), policy)


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
@pytest.mark.parametrize("command", sorted(COVERAGE["commands"]))
def test_displayed_help_matches_manifest(run_gc, entrypoint, command):
    result = run_gc([*command.split(), "--help"], entrypoint=entrypoint)
    assert result.returncode == 0
    assert result.stderr == ""
    assert_surface(parse_help(result.stdout), _node(command), COVERAGE["commands"][command])


@pytest.mark.parametrize("entrypoint", ["gc", "gitcode"])
@pytest.mark.parametrize("group", ["issue", "pr"])
def test_advertised_create_alias_resolves_same_surface(run_gc, entrypoint, group):
    canonical = run_gc([group, "create", "--help"], entrypoint=entrypoint)
    alias = run_gc([group, "new", "--help"], entrypoint=entrypoint)
    assert canonical.returncode == alias.returncode == 0
    assert canonical.stderr == alias.stderr == ""
    canonical_surface = parse_help(canonical.stdout)
    alias_surface = parse_help(alias.stdout)
    assert canonical_surface.pop("usage") == f"cli {group} create [flags]"
    assert alias_surface.pop("usage") == f"cli {group} new [flags]"
    assert canonical_surface == alias_surface
