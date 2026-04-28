from unittest.mock import MagicMock

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
