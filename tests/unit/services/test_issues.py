from unittest.mock import MagicMock

import pytest

from gitcode_cli.services.issues import IssueService


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return IssueService(mock_client)


class TestIssueService:
    def test_init(self, mock_client):
        service = IssueService(mock_client)
        assert service.client is mock_client

    def test_list(self, service, mock_client):
        mock_client.get.return_value = [{"number": "1"}]
        result = service.list("owner", "repo", state="open", per_page=10)

        mock_client.get.assert_called_once_with("/repos/owner/repo/issues", params={"state": "open", "per_page": 10})
        assert result == [{"number": "1"}]

    def test_get(self, service, mock_client):
        mock_client.get.return_value = {"number": "42"}
        result = service.get("owner", "repo", "42")

        mock_client.get.assert_called_once_with("/repos/owner/repo/issues/42")
        assert result == {"number": "42"}

    def test_create(self, service, mock_client):
        mock_client.post.return_value = {"number": "42"}
        result = service.create("owner", "repo", title="Bug", body="Something is broken", assignee=None)

        mock_client.post.assert_called_once_with(
            "/repos/owner/issues",
            json={"repo": "repo", "title": "Bug", "body": "Something is broken"},
        )
        assert result == {"number": "42"}

    def test_update(self, service, mock_client):
        mock_client.patch.return_value = {"number": "42"}
        result = service.update("owner", "repo", "42", title="Updated", state="closed", milestone=None)

        mock_client.patch.assert_called_once_with(
            "/repos/owner/issues/42",
            json={"repo": "repo", "title": "Updated", "state": "closed"},
        )
        assert result == {"number": "42"}

    def test_comment(self, service, mock_client):
        mock_client.post.return_value = {"id": 1}
        result = service.comment("owner", "repo", "42", "Nice issue!")

        mock_client.post.assert_called_once_with("/repos/owner/repo/issues/42/comments", json={"body": "Nice issue!"})
        assert result == {"id": 1}

    def test_delete(self, service, mock_client):
        mock_client.delete.return_value = None
        result = service.delete("owner", "repo", "42")

        mock_client.delete.assert_called_once_with("/repos/owner/repo/issues/42")
        assert result is None
