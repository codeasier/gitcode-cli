"""Parser regressions prove additions, alias swaps and arity cannot pass silently."""

from __future__ import annotations

import copy

import pytest

from .surface import assert_surface, expected_surface, parse_help

pytestmark = [pytest.mark.e2e, pytest.mark.compat]

HELP = """Manage issues.

USAGE
  gc issue <command> [flags]

GENERAL COMMANDS
  create:  Create a new
           issue

FLAGS
  -t, --title TEXT  Supply a title
                   across wrapped lines.
  --draft          Create a draft

INHERITED FLAGS
  --help  Show help for command
"""
NODE = {
    "summary": "Manage issues",
    "flags": [
        {"short": "-t", "long": "--title", "value": "string"},
        {"short": None, "long": "--draft", "value": None},
        {"short": None, "long": "--help", "value": None},
    ],
    "subcommands": [{"path": ["gh", "issue", "create"], "summary": "Create a new issue"}],
}
POLICY = {"gc_invariants": {"usage": "cli issue <command> [flags]", "aliases": []}}


def test_parser_normalizes_wrapping_color_and_binary_name():
    surface = parse_help(HELP)
    colored = "\x1b[32m" + HELP.replace("gc issue", "gitcode issue") + "\x1b[0m"
    assert parse_help(colored) == surface
    assert_surface(surface, NODE, POLICY)
    assert surface["flags"]["-t"] == {"target": "--title", "takes_value": True}
    assert surface["flags"]["--draft"]["takes_value"] is False


@pytest.mark.parametrize("mutation", ["missing", "extra", "alias_target", "arity", "command", "usage", "aliases"])
def test_unregistered_drift_is_rejected(mutation):
    actual = parse_help(HELP)
    if mutation == "missing":
        del actual["flags"]["-t"]
    elif mutation == "extra":
        actual["flags"]["--surprise"] = {"target": "--surprise", "takes_value": False}
    elif mutation == "alias_target":
        actual["flags"]["-t"]["target"] = "--draft"
    elif mutation == "arity":
        actual["flags"]["--draft"]["takes_value"] = True
    elif mutation == "command":
        actual["commands"]["create"] = "Delete an issue"
    elif mutation == "usage":
        actual["usage"] += " <unexpected>"
    else:
        actual["aliases"] = ["cli issue surprise"]
    with pytest.raises(AssertionError):
        assert_surface(actual, NODE, POLICY)


@pytest.mark.parametrize(
    "text",
    [
        HELP + "\nGLOBAL FLAGS\n  --surprise  Unexpected\n",
        HELP + "\nGlobal flags\n  --surprise  Unexpected\n",
        HELP.replace("\nFLAGS\n", "\nOPTIONS\n"),
        HELP.replace("  --draft", "  --surprise  Unexpected\n  --draft"),
        HELP.replace("-t, --title", "--title"),
        HELP.replace("-t, --title", "-t, --other"),
        HELP.replace("--draft", "--draft TEXT"),
        HELP.replace("Create a new", "Remove an old"),
    ],
)
def test_raw_help_mutations_cannot_hide_drift(text):
    with pytest.raises(AssertionError):
        assert_surface(parse_help(text), NODE, POLICY)


@pytest.mark.parametrize("entry", [{"category": "deferred", "reason": ""}, {"category": "unknown", "reason": "why"}])
def test_differences_require_recognized_reason(entry):
    policy = {**POLICY, "missing_flags": {"-t": entry}}
    with pytest.raises(AssertionError):
        expected_surface(NODE, policy)


def test_stale_exception_is_rejected():
    policy = copy.deepcopy(POLICY)
    policy["missing_flags"] = {"--not-in-gh": {"category": "deferred", "reason": "Not implemented"}}
    with pytest.raises(AssertionError, match="Stale missing"):
        expected_surface(NODE, policy)


@pytest.mark.parametrize("text", ["No usage", HELP + "\nUSAGE\n  gc issue\n", HELP.replace("--draft", "--title")])
def test_incomplete_or_duplicate_surface_is_rejected(text):
    with pytest.raises(AssertionError):
        parse_help(text)
