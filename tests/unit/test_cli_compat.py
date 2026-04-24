from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.cli_compat import (
    get_body_from_options,
    get_default_base_branch,
    normalize_multi_values,
    resolve_pr_identifier_or_current_branch,
)


class TestGetBodyFromOptions:
    def test_prefers_inline_body(self, monkeypatch):
        edit_mock = MagicMock()
        monkeypatch.setattr(click, "edit", edit_mock)

        assert get_body_from_options(body="inline", body_file=None, editor=False) == "inline"
        edit_mock.assert_not_called()

    def test_reads_body_from_file(self, tmp_path: Path):
        body_file = tmp_path / "body.md"
        body_file.write_text("file body", encoding="utf-8")

        assert get_body_from_options(body=None, body_file=str(body_file), editor=False) == "file body"

    def test_reads_body_from_stdin_when_body_file_is_dash(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.read", lambda: "stdin body")

        assert get_body_from_options(body=None, body_file="-", editor=False) == "stdin body"

    def test_uses_editor_when_requested(self, monkeypatch):
        monkeypatch.setattr(click, "edit", lambda text=None: "edited body\n")

        assert get_body_from_options(body=None, body_file=None, editor=True) == "edited body\n"

    def test_returns_none_when_editor_is_cancelled(self, monkeypatch):
        monkeypatch.setattr(click, "edit", lambda text=None: None)

        assert get_body_from_options(body=None, body_file=None, editor=True) is None


class TestGetDefaultBaseBranch:
    def test_returns_detected_default_branch(self, monkeypatch):
        monkeypatch.setattr("gitcode_cli.cli_compat.get_default_git_branch", lambda: "main")

        assert get_default_base_branch() == "main"

    def test_raises_click_exception_when_default_branch_cannot_be_detected(self, monkeypatch):
        monkeypatch.setattr("gitcode_cli.cli_compat.get_default_git_branch", lambda: None)

        with pytest.raises(click.ClickException, match="Unable to determine the default base branch"):
            get_default_base_branch()


class TestNormalizeMultiValues:
    def test_returns_none_for_missing_values(self):
        assert normalize_multi_values(None) is None

    def test_returns_single_string_for_one_value(self):
        assert normalize_multi_values(("bug",)) == "bug"

    def test_joins_multiple_values_with_commas(self):
        assert normalize_multi_values(("bug", "docs", "help wanted")) == "bug,docs,help wanted"


class TestResolvePrIdentifierOrCurrentBranch:
    def test_returns_explicit_identifier(self):
        service = MagicMock()

        assert resolve_pr_identifier_or_current_branch("42") == "42"

    def test_uses_current_branch_when_identifier_is_omitted(self, monkeypatch):
        monkeypatch.setattr("gitcode_cli.cli_compat.get_current_git_branch", lambda: "feature/test")
        service = MagicMock()

        assert resolve_pr_identifier_or_current_branch(None) == "feature/test"

    def test_raises_when_current_branch_cannot_be_detected(self, monkeypatch):
        monkeypatch.setattr("gitcode_cli.cli_compat.get_current_git_branch", lambda: None)
        service = MagicMock()

        with pytest.raises(click.ClickException, match="Unable to detect current branch"):
            resolve_pr_identifier_or_current_branch(None)
