from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from gitcode_cli.cli import main

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "gh-cli-compat" / "command_baseline.json"
GH_CLI_BASELINE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _get_cli_flags(command_path: str) -> set[str]:
    result = CliRunner().invoke(main, command_path.split() + ["--help"])
    flags: set[str] = set()
    for line in result.output.splitlines():
        stripped = line.strip()
        if stripped.startswith("-") or stripped.startswith("--"):
            flag = stripped.split(",")[0].split()[0]
            flags.add(flag)
    if not flags:
        raise AssertionError(
            f"No flags parsed from help output for '{command_path}'. "
            f"Exit code: {result.exit_code}, output: {result.output[:300]!r}"
        )
    return flags


def _assert_subcommands(group: str) -> None:
    result = CliRunner().invoke(main, [group, "--help"])
    for command_name in GH_CLI_BASELINE[group]["subcommands"]:
        assert command_name in result.output


def _assert_command_flags(command_path: str) -> None:
    flags = _get_cli_flags(command_path)
    group = command_path.split(maxsplit=1)[0]
    for flag in GH_CLI_BASELINE[group]["commands"][command_path]["flags"]:
        assert flag in flags, f"gh {command_path} flag {flag} missing from gc"


class TestIssueCliGhCompatibility:
    def test_issue_subcommands_exist(self) -> None:
        _assert_subcommands("issue")

    def test_issue_list_has_gh_flags(self) -> None:
        _assert_command_flags("issue list")

    def test_issue_view_has_gh_flags(self) -> None:
        _assert_command_flags("issue view")

    def test_issue_create_has_gh_flags(self) -> None:
        _assert_command_flags("issue create")

    def test_issue_close_has_gh_flags(self) -> None:
        _assert_command_flags("issue close")

    def test_issue_comment_has_gh_flags(self) -> None:
        _assert_command_flags("issue comment")

    def test_issue_list_rejects_invalid_limit(self) -> None:
        result = CliRunner().invoke(main, ["issue", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output


class TestPrCliGhCompatibility:
    def test_pr_subcommands_exist(self) -> None:
        _assert_subcommands("pr")

    def test_pr_list_has_gh_flags(self) -> None:
        _assert_command_flags("pr list")

    def test_pr_view_has_gh_flags(self) -> None:
        _assert_command_flags("pr view")

    def test_pr_create_has_gh_flags(self) -> None:
        _assert_command_flags("pr create")

    def test_pr_close_has_gh_flags(self) -> None:
        _assert_command_flags("pr close")

    def test_pr_merge_has_gh_flags(self) -> None:
        _assert_command_flags("pr merge")

    def test_pr_comment_has_gh_flags(self) -> None:
        _assert_command_flags("pr comment")

    def test_pr_review_has_gh_flags(self) -> None:
        _assert_command_flags("pr review")
