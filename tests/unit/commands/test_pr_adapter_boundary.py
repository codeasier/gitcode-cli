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
    monkeypatch.setattr("gitcode_cli.commands.pr.resolve_repo", lambda x=None: ("owner", "repo"))


@pytest.fixture
def mock_app_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
    return client


class TestPrCommandAdapterBoundary:
    def test_pr_list_delegates_to_adapter(self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock) -> None:
        adapter = MagicMock()
        adapter.list_prs.return_value = [{"number": 1, "state": "open", "title": "First PR"}]

        pull_service_ctor = MagicMock()
        pull_adapter_ctor = MagicMock(return_value=adapter)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("gitcode_cli.commands.pr.PullRequestService", pull_service_ctor)
            mp.setattr("gitcode_cli.commands.pr.PullRequestAdapter", pull_adapter_ctor)
            result = runner.invoke(
                main, ["pr", "list", "-s", "open", "-A", "alice", "-B", "main", "-l", "bug", "-L", "5"]
            )

        assert result.exit_code == 0
        pull_service_ctor.assert_called_once_with(mock_app_client)
        pull_adapter_ctor.assert_called_once_with(pull_service_ctor.return_value)
        adapter.list_prs.assert_called_once_with(
            "owner",
            "repo",
            state="open",
            author="alice",
            base="main",
            assignee=None,
            draft=None,
            head=None,
            labels=("bug",),
            search=None,
            limit=5,
        )

    def test_pr_create_delegates_to_adapter(
        self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock
    ) -> None:
        adapter = MagicMock()
        adapter.create_pr.return_value = type("Result", (), {"item": {"html_url": "https://example.com/pulls/42"}})()

        pull_service_ctor = MagicMock()
        pull_adapter_ctor = MagicMock(return_value=adapter)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("gitcode_cli.commands.pr.PullRequestService", pull_service_ctor)
            mp.setattr("gitcode_cli.commands.pr.PullRequestAdapter", pull_adapter_ctor)
            result = runner.invoke(
                main,
                [
                    "pr",
                    "create",
                    "--title",
                    "Feature",
                    "--body",
                    "Body",
                    "--base",
                    "main",
                    "--head",
                    "feature",
                    "-l",
                    "bug",
                    "-r",
                    "alice",
                    "-a",
                    "bob",
                ],
            )

        assert result.exit_code == 0
        pull_service_ctor.assert_called_once_with(mock_app_client)
        pull_adapter_ctor.assert_called_once_with(pull_service_ctor.return_value)
        adapter.create_pr.assert_called_once_with(
            "owner",
            "repo",
            title="Feature",
            body="Body",
            base="main",
            head="feature",
            draft=False,
            milestone=None,
            labels=("bug",),
            reviewers=("alice",),
            assignees=("bob",),
            dry_run=False,
        )

    def test_pr_review_delegates_to_adapter(
        self, runner: CliRunner, mock_repo: None, mock_app_client: MagicMock
    ) -> None:
        adapter = MagicMock()
        adapter.review_pr.return_value = type(
            "Result", (), {"item": {"state": "APPROVED"}, "degraded": False, "message": None}
        )()

        pull_service_ctor = MagicMock()
        pull_adapter_ctor = MagicMock(return_value=adapter)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("gitcode_cli.commands.pr.PullRequestService", pull_service_ctor)
            mp.setattr("gitcode_cli.commands.pr.PullRequestAdapter", pull_adapter_ctor)
            result = runner.invoke(
                main,
                ["pr", "review", "42", "--approve"],
            )

        assert result.exit_code == 0
        pull_service_ctor.assert_called_once_with(mock_app_client)
        pull_adapter_ctor.assert_called_once_with(pull_service_ctor.return_value)
        adapter.review_pr.assert_called_once_with(
            "owner",
            "repo",
            42,
            approve=True,
            body=None,
            comment=False,
            request_changes=False,
            force=False,
        )
