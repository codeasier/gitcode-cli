"""GitCode v5 project discussion replies, strict offline HTTP only.

https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment/
https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment-comment-id-reply/
"""

from __future__ import annotations

import json
from inspect import signature

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.errors import APIError
from gitcode_cli.services.discussions import DiscussionService

ORIGIN = "https://discuss.gitcode.invalid"
TOKEN = "synthetic-replies-token"
COMMENTS = "/api/v5/repos/Team/Project/discuss/8/comment"
PATH = COMMENTS + "/comment-%E9%9B%AA/reply"


def parent(identity):
    return {"id": identity, "is_hide": 0, "is_deleted": 0}


@pytest.fixture
def strict_http():
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        yield router


@pytest.fixture
def service(strict_http):
    client = GitCodeClient(TOKEN, base_url=f"{ORIGIN}/api/v5/")
    try:
        yield DiscussionService(client, "Team", "Project")
    finally:
        client.close()


def mock_comment_pages(router, *pages):
    def response(request):
        page = int(request.url.params["page"])
        assert request.url.raw_path.split(b"?")[0] == COMMENTS.encode("ascii")
        assert sorted(request.url.params.multi_items()) == sorted(
            [("access_token", TOKEN), ("page", str(page)), ("per_page", "100"), ("order", "time_asc")]
        )
        assert not request.content and request.headers["accept"] == "application/json"
        assert "private-token" not in request.headers and "authorization" not in request.headers
        result = pages[page - 1]
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    return router.get(ORIGIN + COMMENTS).mock(side_effect=response)


@pytest.mark.parametrize("status", [200, 302, 401, 404, 429])
def test_reply_transport_requires_parent_membership_then_one_page_without_fallback(service, strict_http, status):
    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.split(b"?")[0] == PATH.encode("ascii")
        assert sorted(request.url.params.multi_items()) == sorted(
            [("access_token", TOKEN), ("page", "2"), ("per_page", "100")]
        )
        assert not request.content and request.headers["accept"] == "application/json"
        assert "private-token" not in request.headers and "authorization" not in request.headers
        headers = {"location": f"{ORIGIN}/unexpected"} if status == 302 else {}
        return httpx.Response(status, headers=headers, json=[] if status == 200 else {"message": "not available"})

    lookup = mock_comment_pages(strict_http, [parent("comment-雪")])
    route = strict_http.get(ORIGIN + PATH).mock(side_effect=response)
    if status == 200:
        assert service.replies_page(8, "comment-雪", page=2, per_page=100) == []
    else:
        with pytest.raises(APIError) as exc:
            service.replies_page(8, "comment-雪", page=2, per_page=100)
        assert exc.value.status_code == status
    assert lookup.call_count == route.call_count == 1
    assert lookup.calls[0] == strict_http.calls[0]


@pytest.mark.parametrize(
    "number,parent,page,size",
    [
        (False, "parent", 1, 20),
        (8, "../parent", 1, 20),
        (8, "parent", True, 20),
        (8, "parent", 0, 20),
        (8, "parent", 1, False),
        (8, "parent", 1, 101),
    ],
)
def test_reply_service_rejects_invalid_selection_without_transport(service, strict_http, number, parent, page, size):
    with pytest.raises(APIError):
        service.replies_page(number, parent, page=page, per_page=size)
    assert not strict_http.calls


@pytest.fixture
def cli(service, monkeypatch):
    monkeypatch.setattr(AppContext, "client", lambda self: service.client)
    # Click 8.1 mixes output streams unless disabled at runner construction.
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))
    return lambda *args: runner.invoke(
        main, ["--token", TOKEN, "-R", "Team/Project", "discussion", "replies", "8", *args]
    )


@pytest.mark.parametrize("options", [[], ["--json", "id,body"]])
def test_cli_refuses_parent_absent_from_requested_discussion(cli, strict_http, options):
    # Only this discussion's top-level collection is allowed. No reply route,
    # other discussion, repository, or write is registered in strict HTTP.
    lookup = mock_comment_pages(strict_http, [parent("local-comment")])
    result = cli("not-in-this-discussion", *options)
    assert result.exit_code == 1 and not result.stdout_bytes
    assert "not found in the requested discussion" in result.stderr
    assert len(strict_http.calls) == lookup.call_count == 1


def test_cli_later_parent_page_and_requested_reply_page_are_independent(cli, strict_http):
    first = [parent(f"c{i}") for i in range(100)]
    lookup = mock_comment_pages(strict_http, first, [{**parent("comment-雪"), "type": 1, "parent_id": ""}])
    row = {
        "id": "r",
        "created_at": "time",
        "author": {"login": "user"},
        "md_content": "ok",
        "is_hide": 0,
        "is_deleted": 0,
    }
    route = strict_http.get(ORIGIN + PATH, params__contains={"page": 4, "per_page": 1}).respond(200, json=[row])
    result = cli("comment-雪", "--page", "4", "--per-page", "1", "--json", "id")
    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout) == [{"id": "r"}]
    assert [c.request.url.params["page"] for c in lookup.calls] == ["1", "2"]
    assert lookup.calls[1] == strict_http.calls[1] and route.calls[0] == strict_http.calls[2]


@pytest.mark.parametrize("status", [302, 401, 403, 404, 429, 503])
def test_cli_parent_probe_error_stops_without_reply_read(cli, strict_http, status):
    failure = httpx.Response(status, headers={"location": ORIGIN + "/other"}, json={"message": "private diagnostic"})
    lookup = mock_comment_pages(strict_http, [parent(f"c{i}") for i in range(100)], failure)
    result = cli("unverified", "--json", "body")
    assert result.exit_code == 1 and not result.stdout_bytes
    assert str(status) in result.stderr and "private diagnostic" not in result.stderr
    assert len(strict_http.calls) == lookup.call_count == 2


def test_cli_membership_work_is_capped_independently_of_reply_pagination(cli, strict_http):
    pages = [[parent(f"c{p}-{i}") for i in range(100)] for p in range(10)]
    lookup = mock_comment_pages(strict_http, *pages)
    result = cli("unverified", "--page", "30", "--per-page", "1", "--json", "id")
    assert result.exit_code == 1 and not result.stdout_bytes
    assert "page limit" in result.stderr
    assert [c.request.url.params["page"] for c in lookup.calls] == [str(p) for p in range(1, 11)]


def test_repeated_id_on_later_parent_page_fails_even_if_target_present(cli, strict_http):
    lookup = mock_comment_pages(strict_http, [parent(f"c{i}") for i in range(100)], [parent("target"), parent("c0")])
    result = cli("target")
    assert result.exit_code == 1 and not result.stdout_bytes and "repeated" in result.stderr
    assert lookup.call_count == 2


@pytest.mark.parametrize(
    "rows",
    [
        {},
        [parent("c")] * 101,
        [None],
        [{"id": 3}],
        [{"id": "bad/id"}],
        [{"id": "target"}],
        [parent("target"), None],
        [parent("target"), parent("target")],
        [{**parent("target"), "type": 2}],
        [{**parent("target"), "is_hide": 1}],
        [{**parent("target"), "is_deleted": 1}],
        [{**parent("target"), "is_deleted": False}],
    ],
)
def test_cli_malformed_or_nonvisible_membership_never_requests_replies(cli, strict_http, rows):
    lookup = mock_comment_pages(strict_http, rows)
    result = cli("target", "--json", "id")
    assert result.exit_code == 1 and not result.stdout_bytes
    assert "no replies requested" in result.stderr and lookup.call_count == 1


@pytest.mark.parametrize("parent_id", ["other", None, 0, " ", True, [], {}])
@pytest.mark.parametrize("fields", [{}, {"type": 1}])
def test_cli_rejects_explicit_nesting_or_malformed_parent_marker_on_later_page(cli, strict_http, parent_id, fields):
    lookup = mock_comment_pages(
        strict_http, [parent(f"c{i}") for i in range(100)], [{**parent("target"), "parent_id": parent_id, **fields}]
    )
    result = cli("target", "--json", "id,body")
    assert result.exit_code == 1 and not result.stdout_bytes
    assert "no replies requested" in result.stderr
    assert len(strict_http.calls) == lookup.call_count == 2
