from __future__ import annotations

from click.testing import CliRunner

from gitcode_cli.cli import main


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


class TestIssueCliGhCompatibility:
    def test_issue_subcommands_exist(self) -> None:
        result = CliRunner().invoke(main, ["issue", "--help"])
        for cmd in ("list", "view", "create", "close", "comment"):
            assert cmd in result.output

    def test_issue_list_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("issue list")
        for flag in ("-s", "-l", "-A", "-a", "--milestone", "--mention", "-S", "-L", "-w", "--json", "-q", "-t", "-R"):
            assert flag in flags, f"gh issue list flag {flag} missing from gc"

    def test_issue_view_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("issue view")
        for flag in ("-w", "-c", "--json", "-q", "-t", "-R"):
            assert flag in flags, f"gh issue view flag {flag} missing from gc"

    def test_issue_create_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("issue create")
        for flag in ("-t", "-b", "-a", "-l", "-m", "-F", "-w", "--json", "-q", "-t", "-R"):
            assert flag in flags, f"gh issue create flag {flag} missing from gc"

    def test_issue_close_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("issue close")
        for flag in ("-c", "-r", "-R"):
            assert flag in flags, f"gh issue close flag {flag} missing from gc"

    def test_issue_comment_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("issue comment")
        for flag in ("-b", "-F", "-e", "-R"):
            assert flag in flags, f"gh issue comment flag {flag} missing from gc"

    def test_issue_list_rejects_invalid_limit(self) -> None:
        result = CliRunner().invoke(main, ["issue", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output


class TestPrCliGhCompatibility:
    def test_pr_subcommands_exist(self) -> None:
        result = CliRunner().invoke(main, ["pr", "--help"])
        for cmd in ("list", "view", "create", "close", "merge", "comment", "review"):
            assert cmd in result.output

    def test_pr_list_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr list")
        for flag in (
            "-s",
            "-A",
            "-B",
            "--assignee",
            "--draft",
            "--head",
            "-l",
            "-S",
            "-L",
            "-w",
            "--json",
            "-q",
            "-t",
            "-R",
        ):
            assert flag in flags, f"gh pr list flag {flag} missing from gc"

    def test_pr_view_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr view")
        for flag in ("-w", "-c", "--json", "-q", "-t", "-R"):
            assert flag in flags, f"gh pr view flag {flag} missing from gc"

    def test_pr_create_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr create")
        for flag in (
            "-t",
            "-b",
            "-F",
            "-B",
            "-H",
            "-d",
            "--milestone",
            "-l",
            "-r",
            "-a",
            "-w",
            "--json",
            "-q",
            "-t",
            "-R",
        ):
            assert flag in flags, f"gh pr create flag {flag} missing from gc"

    def test_pr_close_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr close")
        for flag in ("-c", "-d", "-R"):
            assert flag in flags, f"gh pr close flag {flag} missing from gc"

    def test_pr_merge_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr merge")
        for flag in ("-m", "-s", "-r", "-d", "-R"):
            assert flag in flags, f"gh pr merge flag {flag} missing from gc"

    def test_pr_comment_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr comment")
        for flag in ("-b", "-F", "-e", "-w", "--path", "--position", "-R"):
            assert flag in flags, f"gh pr comment flag {flag} missing from gc"

    def test_pr_review_accepts_gh_flags(self) -> None:
        flags = _get_cli_flags("pr review")
        for flag in ("-a", "--body", "--comment", "--request-changes", "-R"):
            assert flag in flags, f"gh pr review flag {flag} missing from gc"
