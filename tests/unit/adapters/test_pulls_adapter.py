from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gitcode_cli.adapters.pulls import PullRequestAdapter


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def adapter(service):
    return PullRequestAdapter(service)


class TestPullRequestAdapter:
    def test_list_prs_normalizes_labels(self, adapter, service):
        service.list.return_value = [{"number": 1}]

        result = adapter.list_prs(
            "owner",
            "repo",
            state="open",
            author="alice",
            base="main",
            assignee="bob",
            draft=True,
            head="feature",
            labels=("bug", "docs"),
            search="query",
            limit=1,
        )

        service.list.assert_called_once_with(
            "owner",
            "repo",
            state="open",
            author="alice",
            base="main",
            assignee="bob",
            draft=True,
            head="feature",
            labels="bug,docs",
            search="query",
        )
        assert result == [{"number": 1}]

    def test_create_pr_dry_run_returns_normalized_payload_without_service_call(self, adapter, service):
        result = adapter.create_pr(
            "owner",
            "repo",
            title="Test",
            body="Body",
            base="main",
            head="feature",
            draft=False,
            milestone="v1",
            labels=("bug", "docs"),
            reviewers=("alice", "bob"),
            assignees=("carol", "dave"),
            dry_run=True,
        )

        service.create.assert_not_called()
        assert result.item == {
            "title": "Test",
            "body": "Body",
            "base": "main",
            "head": "feature",
            "draft": False,
            "labels": "bug,docs",
            "assignees": "carol,dave",
            "reviewers": "alice,bob",
            "milestone": "v1",
        }

    def test_review_pr_approve_calls_review_api(self, adapter, service):
        service.review.return_value = {"state": "APPROVED"}

        result = adapter.review_pr(
            "owner",
            "repo",
            42,
            approve=True,
            body="LGTM",
            comment=False,
            request_changes=False,
            force=False,
        )

        service.review.assert_called_once_with("owner", "repo", 42, body="LGTM", force=False)
        assert result.degraded is False
        assert result.item == {"state": "APPROVED"}

    def test_review_pr_comment_degrades_to_regular_comment(self, adapter, service):
        service.comment.return_value = {"id": 7}

        result = adapter.review_pr(
            "owner",
            "repo",
            42,
            approve=False,
            body="needs tests",
            comment=True,
            request_changes=False,
            force=False,
        )

        service.comment.assert_called_once_with("owner", "repo", 42, body="needs tests")
        assert result.degraded is True
        assert result.item == {"id": 7}
        assert "comment reviews" in result.message

    def test_status_returns_approximation_message(self, adapter, service):
        service.list.return_value = [{"number": 1, "state": "open", "title": "Test"}]

        result = adapter.status("owner", "repo")

        assert result.approximated is True
        assert result.message == "GitCode API approximation -- user-specific filtering is not available"
        assert result.items == [{"number": 1, "state": "open", "title": "Test"}]

    def test_edit_pr_maps_add_remove_fields(self, adapter, service):
        service.update.return_value = {"number": 42}

        adapter.edit_pr(
            "owner",
            "repo",
            42,
            title="New title",
            body="Body",
            base="main",
            add_assignee="alice",
            add_label="bug",
            add_reviewer="bob",
            remove_assignee="carol",
            remove_label="wip",
            remove_reviewer="dave",
            milestone="v1",
            remove_milestone=False,
        )

        service.update.assert_called_once_with(
            "owner",
            "repo",
            42,
            title="New title",
            body="Body",
            base="main",
            assignee="alice",
            labels="bug",
            reviewer="bob",
            unassignee="carol",
            unset_labels="wip",
            unset_reviewer="dave",
            milestone="v1",
        )
