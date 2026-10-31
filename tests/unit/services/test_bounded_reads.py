"""Producer primitives do not choose the consuming entry point's result policy."""

from unittest.mock import MagicMock

import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.pulls import PullRequestService

PAGED_READS = [
    (IssueService, "list_comments_page", "I42", "/repos/owner/repo/issues/I42/comments"),
    (PullRequestService, "list_comments_page", 42, "/repos/owner/repo/pulls/42/comments"),
    (PullRequestService, "list_commits_page", 42, "/repos/owner/repo/pulls/42/commits"),
]


@pytest.mark.parametrize(("service_type", "method", "number", "path"), PAGED_READS)
@pytest.mark.parametrize("result", [None, {}, [], [{"id": 1}], [{"id": i} for i in range(100)]])
def test_page_reads_once_and_returns_the_unmodified_result(service_type, method, number, path, result):
    client = MagicMock()
    client.get.return_value = result
    params = {"page": 3, "per_page": 100, "omitted": None}

    assert getattr(service_type(client), method)("owner", "repo", number, **params) is result

    client.get.assert_called_once_with(path, params=params)
    assert params == {"page": 3, "per_page": 100, "omitted": None}


@pytest.mark.parametrize(("service_type", "method", "number", "path"), PAGED_READS)
def test_page_reads_preserve_upstream_defaults_when_no_query_is_supplied(service_type, method, number, path):
    client = MagicMock()
    getattr(service_type(client), method)("owner", "repo", number)
    client.get.assert_called_once_with(path, params={})


@pytest.mark.parametrize("result", [None, {}, [], {"diffs": [], "diff_refs": {"head_sha": "a" * 40}}])
def test_structured_diff_returns_the_raw_envelope_without_paging_or_text_conversion(result):
    client = MagicMock()
    client.get.return_value = result

    assert PullRequestService(client).structured_diff("owner", "repo", 42) is result

    client.get.assert_called_once_with("/repos/owner/repo/pulls/42/files.json")
    client.request.assert_not_called()


@pytest.mark.parametrize(
    ("service_type", "method", "number", "path"),
    [*PAGED_READS, (PullRequestService, "structured_diff", 42, "/repos/owner/repo/pulls/42/files.json")],
)
def test_transport_errors_propagate_without_retry_or_remapping(service_type, method, number, path):
    client = MagicMock()
    error = APIError("Synthetic failure", 429)
    client.get.side_effect = error

    with pytest.raises(APIError) as raised:
        getattr(service_type(client), method)("owner", "repo", number)

    assert raised.value is error
    assert client.get.call_count == 1
    assert client.get.call_args.args == (path,)


class TokenlessOverride(GitCodeClient):
    """A downstream request override need not initialize CLI credential state."""

    def __init__(self):
        self.calls = []

    def request(self, method, path, *, params=None, json=None, accept="application/json", response_format="json"):
        self.calls.append((method, path, params, json, accept, response_format))
        return {"raw": True}


@pytest.mark.parametrize(
    ("service_type", "method", "number", "path"),
    [*PAGED_READS, (PullRequestService, "structured_diff", 42, "/repos/owner/repo/pulls/42/files.json")],
)
def test_primitives_use_the_original_tokenless_request_override(service_type, method, number, path):
    client = TokenlessOverride()
    params = {} if method == "structured_diff" else {"page": 2, "per_page": 5}

    assert getattr(service_type(client), method)("owner", "repo", number, **params) == {"raw": True}

    assert client.calls == [("GET", path, params or None, None, "application/json", "json")]


def test_legacy_issue_comments_still_omit_query_parameters():
    client = MagicMock()
    IssueService(client).list_comments("owner", "repo", "I42")
    client.get.assert_called_once_with("/repos/owner/repo/issues/I42/comments")
