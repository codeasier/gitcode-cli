from __future__ import annotations

from unittest.mock import MagicMock, call

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
        service.list.return_value = [{"number": "1", "labels": [{"name": "bug"}, {"name": "docs"}]}]

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
        assert result == [{"number": "1", "labels": [{"name": "bug"}, {"name": "docs"}]}]

    def test_list_issues_filters_repeated_labels_with_and_semantics(self, adapter, service):
        service.list.return_value = [
            {"number": "1", "labels": [{"name": "bug"}, {"name": "docs"}]},
            {"number": "2", "labels": [{"name": "bug"}]},
        ]

        result = adapter.list_issues(
            "owner",
            "repo",
            state="open",
            labels=("bug", "docs"),
            author=None,
            assignee=None,
            milestone=None,
            mention=None,
            search=None,
            limit=None,
        )

        assert result == [{"number": "1", "labels": [{"name": "bug"}, {"name": "docs"}]}]

    def test_list_issues_resolves_author_me_to_current_login(self, adapter, service, user_service):
        user_service.current.return_value = {"login": "alice"}
        service.list.return_value = [{"number": "1"}]

        adapter.list_issues(
            "owner",
            "repo",
            state="open",
            labels=None,
            author="@me",
            assignee=None,
            milestone=None,
            mention=None,
            search=None,
            limit=None,
        )

        user_service.current.assert_called_once_with()
        service.list.assert_called_once_with(
            "owner",
            "repo",
            state="open",
            labels=None,
            creator="alice",
            assignee=None,
            milestone=None,
            mention=None,
            search=None,
        )

    def test_create_issue_normalizes_labels(self, adapter, service):
        service.list_labels.return_value = [{"name": "bug"}, {"name": "docs"}]

        adapter.create_issue(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee="alice",
            labels=(" bug ", "docs"),
            milestone="1",
        )

        service.list_labels.assert_called_once_with("owner", "repo", page=1, per_page=100)
        service.create.assert_called_once_with(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee="alice",
            labels="bug,docs",
            milestone=1,
        )

    def test_create_issue_rejects_unknown_label(self, adapter, service):
        service.list_labels.return_value = [{"name": "bug"}]

        with pytest.raises(Exception, match="could not add label: 'missing' not found"):
            adapter.create_issue(
                "owner",
                "repo",
                title="Bug",
                body="Body",
                assignee=None,
                labels=("missing",),
                milestone=None,
            )

        service.create.assert_not_called()

    def test_create_issue_resolves_milestone_name(self, adapter, service):
        service.list_milestones.return_value = [{"title": "v1.0", "number": 7}]

        adapter.create_issue(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=None,
            milestone="v1.0",
        )

        service.list_milestones.assert_called_once_with("owner", "repo", state="all", page=1, per_page=100)
        service.create.assert_called_once_with(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=None,
            milestone=7,
        )

    def test_create_issue_resolves_milestone_name_when_number_is_string(self, adapter, service):
        service.list_milestones.return_value = [{"title": "v1.0", "number": "7"}]

        adapter.create_issue(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=None,
            milestone="v1.0",
        )

        service.create.assert_called_once_with(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=None,
            milestone=7,
        )

    def test_create_issue_reads_label_pages_until_exhausted(self, adapter, service):
        service.list_labels.side_effect = [
            [{"name": f"label-{index}"} for index in range(100)],
            [{"name": "target"}],
        ]

        adapter.create_issue(
            "owner",
            "repo",
            title="Bug",
            body="Body",
            assignee=None,
            labels=("target",),
            milestone=None,
        )

        assert service.list_labels.call_args_list == [
            call("owner", "repo", page=1, per_page=100),
            call("owner", "repo", page=2, per_page=100),
        ]
        service.create.assert_called_once()

    def test_delete_issue_calls_service_delete(self, adapter, service):
        service.delete.return_value = {"success": True}

        result = adapter.delete_issue("owner", "repo", "42")

        service.delete.assert_called_once_with("owner", "repo", "42")
        assert result.item == {"success": True}
        assert result.message == "deleted"

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
            remove_assignee=None,
            remove_labels=None,
            milestone=None,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", labels="existing,bug,docs")

    def test_edit_issue_removes_labels(self, adapter, service):
        service.get.return_value = {"labels": [{"name": "existing"}, {"name": "bug"}, {"name": "docs"}]}
        service.update.return_value = {"number": "42"}

        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=None,
            remove_assignee=None,
            remove_labels=("bug",),
            milestone=None,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", labels="existing,docs")

    def test_edit_issue_adds_and_removes_labels(self, adapter, service):
        service.get.return_value = {"labels": [{"name": "existing"}, {"name": "bug"}]}
        service.update.return_value = {"number": "42"}

        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=("docs",),
            remove_assignee=None,
            remove_labels=("bug",),
            milestone=None,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", labels="existing,docs")

    def test_edit_issue_removes_assignee_from_existing_assignees(self, adapter, service):
        service.get.return_value = {"assignee": "alice,bob"}

        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=None,
            remove_assignee="bob",
            remove_labels=None,
            milestone=None,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", assignee="alice")

    def test_edit_issue_sets_milestone_number(self, adapter, service):
        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=None,
            remove_assignee=None,
            remove_labels=None,
            milestone=1,
            remove_milestone=False,
        )

        service.update.assert_called_once_with("owner", "repo", "42", milestone=1)

    def test_edit_issue_removes_milestone_with_zero(self, adapter, service):
        adapter.edit_issue(
            "owner",
            "repo",
            "42",
            title=None,
            body=None,
            add_assignee=None,
            add_labels=None,
            remove_assignee=None,
            remove_labels=None,
            milestone=None,
            remove_milestone=True,
        )

        service.update.assert_called_once_with("owner", "repo", "42", milestone=0)

    def test_develop_returns_browser_fallback_message(self, adapter):
        result = adapter.develop("owner", "repo", "42", base="main", name="feature")

        assert result.message == "Opening issue #42 in the browser instead."
        assert result.warning == "Note: 'issue develop' does not create a local branch on GitCode."

    def test_status_returns_grouped_user_context(self, adapter, service, user_service):
        user_service.current.return_value = {"login": "alice"}
        service.list_user_issues.side_effect = [
            [{"number": "1", "state": "open", "title": "Assigned"}],
            [{"number": "2", "state": "open", "title": "Created"}],
        ]
        service.list.return_value = [{"number": "3", "state": "open", "title": "Mentioned"}]

        result = adapter.status("owner", "repo")

        assert result.approximated is True
        assert result.message == (
            "GitCode-limited approximation of gh issue status: assigned and opened issues use user-level "
            "GitCode results; mentioned issues use repository mention filtering."
        )
        assert result.item == {
            "assigned": [{"number": "1", "state": "open", "title": "Assigned"}],
            "mentioned": [{"number": "3", "state": "open", "title": "Mentioned"}],
            "createdBy": [{"number": "2", "state": "open", "title": "Created"}],
        }
        assert service.list_user_issues.call_args_list == [
            call(filter="assigned", state="open"),
            call(filter="created", state="open"),
        ]
        service.list.assert_called_once_with("owner", "repo", state="open", mention="alice")
