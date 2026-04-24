"""Shared pytest fixtures for gitcode_cli tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.services import IssueService, PullRequestService


@pytest.fixture
def mock_token() -> str:
    return "test-token-123"


@pytest.fixture
def mock_client(mock_token: str) -> GitCodeClient:
    return GitCodeClient(token=mock_token, base_url="https://api.gitcode.com/api/v5/")


@pytest.fixture
def mock_context(mock_token: str) -> AppContext:
    return AppContext(token=mock_token, repo=None)


@pytest.fixture
def issue_service(mock_client: GitCodeClient) -> IssueService:
    return IssueService(mock_client)


@pytest.fixture
def pull_service(mock_client: GitCodeClient) -> PullRequestService:
    return PullRequestService(mock_client)


@pytest.fixture
def mock_issue_data() -> dict:
    return {
        "number": "42",
        "title": "Test Issue",
        "state": "open",
        "body": "Issue body",
        "html_url": "https://gitcode.com/owner/repo/issues/42",
    }


@pytest.fixture
def mock_pr_data() -> dict:
    return {
        "number": 42,
        "title": "Test PR",
        "state": "open",
        "body": "PR body",
        "html_url": "https://gitcode.com/owner/repo/pulls/42",
        "head": {"ref": "feature-branch"},
        "base": {"ref": "master"},
    }


@pytest.fixture
def mock_issues_list() -> list[dict]:
    return [
        {"number": "1", "title": "First Issue", "state": "open"},
        {"number": "2", "title": "Second Issue", "state": "closed"},
    ]


@pytest.fixture
def mock_prs_list() -> list[dict]:
    return [
        {"number": 1, "title": "First PR", "state": "open"},
        {"number": 2, "title": "Second PR", "state": "closed"},
    ]


@pytest.fixture
def tmp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config directory to a temp path."""
    config_dir = tmp_path / ".config" / "gc"
    config_dir.mkdir(parents=True)
    import gitcode_cli.config as config_module

    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_dir / "config.json")
    return config_dir


@pytest.fixture
def cli_runner():
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture
def mock_app_context(mock_token: str, monkeypatch: pytest.MonkeyPatch):
    """Patch AppContext.client to avoid real HTTP calls in command tests."""
    from gitcode_cli import context

    original_client = context.AppContext.client

    def mock_client_method(self):
        client = MagicMock()
        client.get = MagicMock(return_value={})
        client.post = MagicMock(return_value={})
        client.patch = MagicMock(return_value={})
        client.put = MagicMock(return_value={})
        client.delete = MagicMock(return_value=None)
        return client

    monkeypatch.setattr(context.AppContext, "client", mock_client_method)
    yield
    monkeypatch.setattr(context.AppContext, "client", original_client)
