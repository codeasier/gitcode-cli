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


GH_ISSUE_LIST_FLAGS = {
    "-s",
    "-l",
    "-A",
    "-a",
    "--milestone",
    "--mention",
    "--app",
    "-S",
    "-L",
    "-w",
    "--json",
    "-q",
    "-t",
    "-R",
}

GH_ISSUE_VIEW_FLAGS = {"-c", "-w", "--json", "-q", "-t", "-R"}

GH_ISSUE_CREATE_FLAGS = {
    "-t",
    "-b",
    "-F",
    "-e",
    "-l",
    "-m",
    "-a",
    "-w",
    "-R",
}

GH_ISSUE_CLOSE_FLAGS = {"-c", "-r", "--duplicate-of", "-R"}

GH_ISSUE_COMMENT_FLAGS = {"-b", "-F", "-e", "-w", "--delete-last", "--edit-last", "-R"}


class TestIssueCliGhCompatibility:
    def test_issue_subcommands_exist(self) -> None:
        result = CliRunner().invoke(main, ["issue", "--help"])
        for cmd in ("list", "view", "create", "close", "comment"):
            assert cmd in result.output

    def test_issue_list_has_gh_flags(self) -> None:
        flags = _get_cli_flags("issue list")
        for flag in GH_ISSUE_LIST_FLAGS:
            assert flag in flags, f"gh issue list flag {flag} missing from gc"

    def test_issue_view_has_gh_flags(self) -> None:
        flags = _get_cli_flags("issue view")
        for flag in GH_ISSUE_VIEW_FLAGS:
            assert flag in flags, f"gh issue view flag {flag} missing from gc"

    def test_issue_create_has_gh_flags(self) -> None:
        flags = _get_cli_flags("issue create")
        for flag in GH_ISSUE_CREATE_FLAGS:
            assert flag in flags, f"gh issue create flag {flag} missing from gc"

    def test_issue_close_has_gh_flags(self) -> None:
        flags = _get_cli_flags("issue close")
        for flag in GH_ISSUE_CLOSE_FLAGS:
            assert flag in flags, f"gh issue close flag {flag} missing from gc"

    def test_issue_comment_has_gh_flags(self) -> None:
        flags = _get_cli_flags("issue comment")
        for flag in GH_ISSUE_COMMENT_FLAGS:
            assert flag in flags, f"gh issue comment flag {flag} missing from gc"

    def test_issue_list_rejects_invalid_limit(self) -> None:
        result = CliRunner().invoke(main, ["issue", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output


GH_PR_LIST_FLAGS = {
    "-s",
    "-A",
    "-B",
    "-a",
    "-d",
    "-H",
    "-l",
    "-S",
    "-L",
    "-w",
    "--json",
    "-q",
    "-t",
    "-R",
}

GH_PR_VIEW_FLAGS = {"-c", "-w", "--json", "-q", "-t", "-R"}

GH_PR_CREATE_FLAGS = {
    "-t",
    "-b",
    "-F",
    "-e",
    "-f",
    "-d",
    "-B",
    "-H",
    "-l",
    "-r",
    "-a",
    "-m",
    "-w",
    "--json",
    "-q",
    "-R",
    "--dry-run",
}

GH_PR_CLOSE_FLAGS = {"-c", "-d", "-R"}

GH_PR_MERGE_FLAGS = {
    "-m",
    "-s",
    "-r",
    "-d",
    "-b",
    "-F",
    "-t",
    "-A",
    "--auto",
    "--admin",
    "-R",
}

GH_PR_COMMENT_FLAGS = {"-b", "-F", "-e", "-w", "-R"}

GH_PR_REVIEW_FLAGS = {"-a", "-b", "-F", "-c", "-r", "-R"}


class TestPrCliGhCompatibility:
    def test_pr_subcommands_exist(self) -> None:
        result = CliRunner().invoke(main, ["pr", "--help"])
        for cmd in ("list", "view", "create", "close", "merge", "comment", "review"):
            assert cmd in result.output

    def test_pr_list_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr list")
        for flag in GH_PR_LIST_FLAGS:
            assert flag in flags, f"gh pr list flag {flag} missing from gc"

    def test_pr_view_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr view")
        for flag in GH_PR_VIEW_FLAGS:
            assert flag in flags, f"gh pr view flag {flag} missing from gc"

    def test_pr_create_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr create")
        for flag in GH_PR_CREATE_FLAGS:
            assert flag in flags, f"gh pr create flag {flag} missing from gc"

    def test_pr_close_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr close")
        for flag in GH_PR_CLOSE_FLAGS:
            assert flag in flags, f"gh pr close flag {flag} missing from gc"

    def test_pr_merge_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr merge")
        for flag in GH_PR_MERGE_FLAGS:
            assert flag in flags, f"gh pr merge flag {flag} missing from gc"

    def test_pr_comment_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr comment")
        for flag in GH_PR_COMMENT_FLAGS:
            assert flag in flags, f"gh pr comment flag {flag} missing from gc"

    def test_pr_review_has_gh_flags(self) -> None:
        flags = _get_cli_flags("pr review")
        for flag in GH_PR_REVIEW_FLAGS:
            assert flag in flags, f"gh pr review flag {flag} missing from gc"
