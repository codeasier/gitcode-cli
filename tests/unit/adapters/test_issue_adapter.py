from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gitcode_cli.adapters.issues import IssueAdapter


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def adapter(service):
    return IssueAdapter(service)


class TestIssueAdapter:
    def test_list_issues_maps_author_to_creator_and_normalizes_labels(self, adapter, service):
        service.list.return_value = [{"number": "1"}]

        result = adapter.list_issues(
            "owner",
            "repo",
            state="open",
            labels=("bug", "docs"),
            author="alice",
            assignee="bob",
            milestone="v1",
            mention="carol",
            search="query",
            limit=1,
        )

        service.list.assert_called_once_with(
            "owner",
            "repo",
            state="open",
            labels="bug,docs",
            creator="alice",
            assignee="bob",
            milestone="v1",
            mention="carol",
            search="query",
        )
        assert result == [{"number": "1"}]

    def test_create_issue_normalizes_labels(self, adapter, service):
        adapter.create_issue(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee="alice",
            labels=("bug", "docs"),
            milestone="v1",
        )

        service.create.assert_called_once_with(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee="alice",
            labels="bug,docs",
            milestone="v1",
        )

    def test_edit_issue_merges_existing_labels(self, adapter, service):
        service.get.return_value = {"labels": [{"name": "existing"}, {"name": "bug"}]}
        service.update.return_value = {"number": "42"}

        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=("bug", "docs"),
            milestone=None,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", labels="existing,bug,docs")

    def test_develop_rejects_base_and_name_through_capability_policy(self, adapter):
        with pytest.raises(Exception) as base_exc:
            adapter.develop("owner", "repo", "42", base="main", name=None)
        assert "--base" in str(base_exc.value)

        with pytest.raises(Exception) as name_exc:
            adapter.develop("owner", "repo", "42", base=None, name="feature")
        assert "--name" in str(name_exc.value)

    def test_status_returns_approximation_message(self, adapter, service):
        service.list.return_value = [{"number": "1", "state": "open", "title": "Test"}]

        result = adapter.status("owner", "repo")

        assert result.approximated is True
        assert result.message == "GitCode-limited approximation of gh issue status"
        assert result.items == [{"number": "1", "state": "open", "title": "Test"}]
