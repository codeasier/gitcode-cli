from unittest.mock import MagicMock

import httpx
import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.repos import RepoService
from gitcode_cli.services.webhooks import WebhookService


def test_complete_comments_read_beyond_first_page():
    client = MagicMock()
    client.get.side_effect = [[{"id": i, "body": "comment"} for i in range(100)], [{"id": 100, "body": "valid"}]]
    result = IssueService(client).list_all_comments("owner", "repo", "42")
    assert len(result) == 101
    client.get.assert_called_with("/repos/owner/repo/issues/42/comments", params={"page": 2, "per_page": 100})


@pytest.mark.parametrize("bad", [None, {}, ["not an object"], [{"body": "no identity"}]])
def test_incomplete_comments_are_not_empty(bad):
    client = MagicMock()
    client.get.return_value = bad
    with pytest.raises(APIError):
        IssueService(client).list_all_comments("owner", "repo", "42")


def test_repeated_page_is_not_complete():
    client = MagicMock()
    client.get.return_value = [{"id": i} for i in range(100)]
    with pytest.raises(APIError, match="Repeated"):
        IssueService(client).list_all_comments("owner", "repo", "42")


def test_overlapping_pages_are_not_complete():
    client = MagicMock()
    client.get.side_effect = [[{"id": i} for i in range(100)], [{"id": 99}, {"id": 100}]]
    with pytest.raises(APIError, match="Duplicate"):
        IssueService(client).list_all_comments("owner", "repo", "42")


def test_remove_label_is_targeted_and_encoded():
    client = MagicMock()
    IssueService(client).remove_label("owner", "repo", "42", "needs / audit")
    client.delete.assert_called_once_with("/repos/owner/repo/issues/42/labels/needs%20%2F%20audit")
    client.patch.assert_not_called()


@pytest.mark.parametrize("name", ["", "bug,resolved"])
def test_remove_label_rejects_batch(name):
    client = MagicMock()
    with pytest.raises(ValueError):
        IssueService(client).remove_label("owner", "repo", "42", name)
    client.delete.assert_not_called()


@pytest.fixture
def transport_client():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(204)

    client = GitCodeClient("synthetic")
    client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        yield client, requests
    finally:
        client.close()


@pytest.mark.parametrize("name", [".", ".."])
def test_remove_label_rejects_dot_segments_before_transport(name, transport_client):
    client, requests = transport_client
    with pytest.raises(ValueError, match="Label name cannot be"):
        IssueService(client).remove_label("owner", "repo", "42", name)
    assert requests == []


@pytest.mark.parametrize(
    ("name", "encoded"),
    [
        ("resolved", "resolved"),
        ("needs / audit", "needs%20%2F%20audit"),
        ("v1.2", "v1.2"),
        (".hidden", ".hidden"),
        ("...", "..."),
        ("%2e%2e", "%252e%252e"),
        ("a?b#c%", "a%3Fb%23c%25"),
    ],
)
def test_remove_label_transport_targets_only_one_encoded_label(name, encoded, transport_client):
    client, requests = transport_client
    assert IssueService(client).remove_label("owner", "repo", "42", name) is None
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "DELETE"
    assert request.url.raw_path.split(b"?", 1)[0] == f"/api/v5/repos/owner/repo/issues/42/labels/{encoded}".encode()
    assert request.content == b""


def test_get_branch_encodes_slashes():
    client = MagicMock()
    RepoService(client).get_branch("owner", "repo", "release/1")
    client.get.assert_called_once_with("/repos/owner/repo/branches/release%2F1")


def test_hooks_forward_payload_and_collect_pages():
    client = MagicMock()
    client.get.return_value = []
    service = WebhookService(client)
    assert service.list_all("owner", "repo") == []
    service.create("owner", "repo", url="https://example.test/hook", issues_events=True, encryption_type=0)
    client.post.assert_called_once_with(
        "/repos/owner/repo/hooks",
        json={"url": "https://example.test/hook", "issues_events": True, "encryption_type": 0},
    )


def test_client_close():
    client = GitCodeClient("synthetic")
    client.close()
    assert client._client.is_closed
