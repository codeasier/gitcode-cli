from unittest.mock import MagicMock, call

import pytest

from gitcode_cli.services.pulls import PullRequestService


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return PullRequestService(mock_client)


class TestPullRequestService:
    def test_init(self, mock_client):
        service = PullRequestService(mock_client)
        assert service.client is mock_client

    def test_list(self, service, mock_client):
        mock_client.get.return_value = [{"number": 1}]
        result = service.list("owner", "repo", state="open")

        mock_client.get.assert_called_once_with("/repos/owner/repo/pulls", params={"state": "open"})
        assert result == [{"number": 1}]

    def test_get(self, service, mock_client):
        mock_client.get.return_value = {"number": 42}
        result = service.get("owner", "repo", 42)

        mock_client.get.assert_called_once_with("/repos/owner/repo/pulls/42")
        assert result == {"number": 42}

    def test_list_issues(self, service, mock_client):
        mock_client.get.return_value = [{"number": "7"}]
        result = service.list_issues("owner", "repo", 42)

        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/pulls/42/issues",
            params={"page": 1, "per_page": 100},
        )
        assert result == [{"number": "7"}]

    def test_list_issues_fetches_all_pages(self, service, mock_client):
        first_page = [{"number": i} for i in range(100)]
        second_page = [{"number": 100}]
        mock_client.get.side_effect = [first_page, second_page]

        result = service.list_issues("owner", "repo", 42)

        assert result == [*first_page, *second_page]
        assert mock_client.get.call_args_list == [
            call("/repos/owner/repo/pulls/42/issues", params={"page": 1, "per_page": 100}),
            call("/repos/owner/repo/pulls/42/issues", params={"page": 2, "per_page": 100}),
        ]

    def test_list_files(self, service, mock_client):
        mock_client.get.return_value = [{"filename": "tests/foo_test.py", "additions": "3", "deletions": "1"}]
        result = service.list_files("owner", "repo", 42)

        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/pulls/42/files",
            params={"page": 1, "per_page": 100},
        )
        assert result[0]["filename"] == "tests/foo_test.py"

    def test_list_files_fetches_all_pages(self, service, mock_client):
        first_page = [{"filename": f"src/file_{i}.py", "additions": 1, "deletions": 0} for i in range(100)]
        second_page = [{"filename": "tests/foo_test.py", "additions": 2, "deletions": 1}]
        mock_client.get.side_effect = [first_page, second_page]

        result = service.list_files("owner", "repo", 42)

        assert result == [*first_page, *second_page]
        assert mock_client.get.call_args_list == [
            call("/repos/owner/repo/pulls/42/files", params={"page": 1, "per_page": 100}),
            call("/repos/owner/repo/pulls/42/files", params={"page": 2, "per_page": 100}),
        ]

    def test_create(self, service, mock_client):
        mock_client.post.return_value = {"number": 42}
        result = service.create("owner", "repo", title="Feature", head="dev", base="master", body=None)

        mock_client.post.assert_called_once_with(
            "/repos/owner/repo/pulls",
            json={"title": "Feature", "head": "dev", "base": "master"},
        )
        assert result == {"number": 42}

    def test_update(self, service, mock_client):
        mock_client.patch.return_value = {"number": 42}
        result = service.update("owner", "repo", 42, title="Updated PR", state="closed", assignee=None)

        mock_client.patch.assert_called_once_with(
            "/repos/owner/repo/pulls/42",
            json={"title": "Updated PR", "state": "closed"},
        )
        assert result == {"number": 42}

    def test_merge(self, service, mock_client):
        mock_client.put.return_value = {"merged": True}
        result = service.merge("owner", "repo", 42, merge_method="squash", title=None)

        mock_client.put.assert_called_once_with("/repos/owner/repo/pulls/42/merge", json={"merge_method": "squash"})
        assert result == {"merged": True}

    def test_comment_without_path_and_position(self, service, mock_client):
        mock_client.post.return_value = {"id": 1}
        result = service.comment("owner", "repo", 42, "LGTM")

        mock_client.post.assert_called_once_with("/repos/owner/repo/pulls/42/comments", json={"body": "LGTM"})
        assert result == {"id": 1}

    def test_comment_with_path_and_position(self, service, mock_client):
        mock_client.post.return_value = {"id": 2}
        result = service.comment("owner", "repo", 42, "Fix this", path="main.py", position=5)

        mock_client.post.assert_called_once_with(
            "/repos/owner/repo/pulls/42/comments",
            json={"body": "Fix this", "path": "main.py", "position": 5},
        )
        assert result == {"id": 2}

    def test_review_without_force(self, service, mock_client):
        mock_client.post.return_value = {"state": "APPROVED"}
        result = service.review("owner", "repo", 42)

        mock_client.post.assert_called_once_with("/repos/owner/repo/pulls/42/review", json={"force": False})
        assert result == {"state": "APPROVED"}

    def test_review_with_force(self, service, mock_client):
        mock_client.post.return_value = {"state": "APPROVED"}
        result = service.review("owner", "repo", 42, force=True)

        mock_client.post.assert_called_once_with("/repos/owner/repo/pulls/42/review", json={"force": True})
        assert result == {"state": "APPROVED"}

    def test_list_comments_fetches_all_pages(self, service, mock_client):
        first_page = [{"id": i} for i in range(100)]
        second_page = [{"id": 100}, {"id": 101}]
        mock_client.get.side_effect = [first_page, second_page]

        result = service.list_comments("owner", "repo", 42)

        assert result == [*first_page, *second_page]
        assert mock_client.get.call_args_list == [
            call("/repos/owner/repo/pulls/42/comments", params={"page": 1, "per_page": 100}),
            call("/repos/owner/repo/pulls/42/comments", params={"page": 2, "per_page": 100}),
        ]

    def test_list_comments_keeps_fetched_pages_when_next_page_is_not_a_list(self, service, mock_client):
        first_page = [{"id": i} for i in range(100)]
        mock_client.get.side_effect = [first_page, None]

        result = service.list_comments("owner", "repo", 42)

        assert result == first_page
        assert mock_client.get.call_args_list == [
            call("/repos/owner/repo/pulls/42/comments", params={"page": 1, "per_page": 100}),
            call("/repos/owner/repo/pulls/42/comments", params={"page": 2, "per_page": 100}),
        ]

    def test_diff_returns_empty_string_for_none(self, service, mock_client):
        mock_client.request.return_value = None
        result = service.diff("owner", "repo", 42)

        mock_client.request.assert_called_once_with(
            "GET",
            "/repos/owner/repo/pulls/42/diff",
            accept="text/plain",
            response_format="text",
        )
        assert result == ""

    def test_diff_requests_text_response(self, service, mock_client):
        mock_client.request.return_value = "diff --git a/file b/file"
        result = service.diff("owner", "repo", 42)

        mock_client.request.assert_called_once_with(
            "GET",
            "/repos/owner/repo/pulls/42/diff",
            accept="text/plain",
            response_format="text",
        )
        assert result == "diff --git a/file b/file"
