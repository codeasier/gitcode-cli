from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gitcode_cli.adapters.issues import IssueAdapter


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def user_service():
    return MagicMock()


@pytest.fixture
def adapter(service, user_service):
    return IssueAdapter(service, user_service)


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

    def test_manage_comment_history_edits_last_owned_comment(self, adapter, service, user_service):
        user_service.current.return_value = {"login": "alice"}
        service.list_comments.return_value = [
            {"id": 1, "user": {"login": "bob"}},
            {"id": 2, "user": {"login": "alice"}},
        ]
        service.update_comment.return_value = {"id": 2, "body": "updated"}

        result = adapter.manage_comment_history(
            "owner",
            "repo",
            "42",
            body="updated",
            delete_last=False,
            create_if_none=False,
        )

        service.update_comment.assert_called_once_with("owner", "repo", 2, "updated")
        assert result.message == "edited"

    def test_manage_comment_history_creates_when_none_and_allowed(self, adapter, service, user_service):
        user_service.current.return_value = {"login": "alice"}
        service.list_comments.return_value = [{"id": 1, "user": {"login": "bob"}}]
        service.comment.return_value = {"id": 3, "html_url": "https://example.com/comments/3"}

        result = adapter.manage_comment_history(
            "owner",
            "repo",
            "42",
            body="new comment",
            delete_last=False,
            create_if_none=True,
        )

        service.comment.assert_called_once_with("owner", "repo", "42", "new comment")
        assert result.message == "created"

    def test_manage_comment_history_deletes_last_owned_comment(self, adapter, service, user_service):
        user_service.current.return_value = {"login": "alice"}
        service.list_comments.return_value = [{"id": 2, "author": {"login": "alice"}}]

        result = adapter.manage_comment_history(
            "owner",
            "repo",
            "42",
            body=None,
            delete_last=True,
            create_if_none=False,
        )

        service.delete_comment.assert_called_once_with("owner", "repo", 2)
        assert result.message == "deleted"

    def test_manage_comment_history_refuses_when_current_user_cannot_be_verified(self, service):
        adapter = IssueAdapter(service, None)

        with pytest.raises(Exception) as exc:
            adapter.manage_comment_history(
                "owner",
                "repo",
                "42",
                body="updated",
                delete_last=False,
                create_if_none=False,
            )

        assert "refusing to edit or delete comments safely" in str(exc.value)

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
