from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gitcode_cli.commands.issue.resolve_repo", lambda x=None: ("owner", "repo"))


@pytest.fixture
def mock_app_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
    return client


class TestIssueCommandAdapterBoundary:
    def test_issue_list_delegates_to_adapter(
        self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock
    ) -> None:
        adapter = MagicMock()
        adapter.list_issues.return_value = [{"number": "1", "state": "open", "title": "First"}]

        issue_service_ctor = MagicMock()
        issue_adapter_ctor = MagicMock(return_value=adapter)

        with (
            pytest.MonkeyPatch.context() as mp,
        ):
            mp.setattr("gitcode_cli.commands.issue.IssueService", issue_service_ctor)
            mp.setattr("gitcode_cli.commands.issue.IssueAdapter", issue_adapter_ctor)
            result = runner.invoke(
                main,
                ["issue", "list", "-s", "open", "-l", "bug", "-A", "alice", "-L", "5"],
            )

        assert result.exit_code == 0
        issue_service_ctor.assert_called_once_with(mock_app_client)
        issue_adapter_ctor.assert_called_once_with(issue_service_ctor.return_value)
        adapter.list_issues.assert_called_once_with(
            "owner",
            "repo",
            state="open",
            labels=("bug",),
            author="alice",
            assignee=None,
            milestone=None,
            mention=None,
            search=None,
            limit=5,
        )

    def test_issue_create_delegates_to_adapter(
        self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock
    ) -> None:
        adapter = MagicMock()
        adapter.create_issue.return_value = {"html_url": "https://example.com/issues/42"}

        issue_service_ctor = MagicMock()
        issue_adapter_ctor = MagicMock(return_value=adapter)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("gitcode_cli.commands.issue.IssueService", issue_service_ctor)
            mp.setattr("gitcode_cli.commands.issue.IssueAdapter", issue_adapter_ctor)
            result = runner.invoke(
                main,
                ["issue", "create", "-t", "Bug", "-b", "Body", "-l", "bug", "-m", "v1"],
            )

        assert result.exit_code == 0
        issue_service_ctor.assert_called_once_with(mock_app_client)
        issue_adapter_ctor.assert_called_once_with(issue_service_ctor.return_value)
        adapter.create_issue.assert_called_once_with(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=("bug",),
            milestone="v1",
        )

    def test_issue_close_delegates_to_adapter(
        self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock
    ) -> None:
        adapter = MagicMock()
        adapter.close_issue.return_value = type("Result", (), {"message": "closed", "item": {"number": "42"}})()

        issue_service_ctor = MagicMock()
        issue_adapter_ctor = MagicMock(return_value=adapter)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("gitcode_cli.commands.issue.IssueService", issue_service_ctor)
            mp.setattr("gitcode_cli.commands.issue.IssueAdapter", issue_adapter_ctor)
            result = runner.invoke(
                main,
                ["issue", "close", "42", "-c", "done", "-r", "completed"],
            )

        assert result.exit_code == 0
        issue_service_ctor.assert_called_once_with(mock_app_client)
        issue_adapter_ctor.assert_called_once_with(issue_service_ctor.return_value)
        adapter.close_issue.assert_called_once_with(
            "owner",
            "repo",
            "42",
            comment="done",
            reason="completed",
        )
