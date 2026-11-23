"""GitCode v5 project discussion replies, strict offline HTTP only.

https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment-comment-id-reply/
"""

from __future__ import annotations

import httpx
import pytest
import respx

from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.discussions import DiscussionService

ORIGIN = "https://discuss.gitcode.invalid"
TOKEN = "synthetic-replies-token"
PATH = "/api/v5/repos/Team/Project/discuss/8/comment/comment-%E9%9B%AA/reply"


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


@pytest.mark.parametrize("status", [200, 302, 401, 404, 429])
def test_reply_transport_is_one_scoped_read_without_fallback(service, strict_http, status):
    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.split(b"?")[0] == PATH.encode("ascii")
        assert sorted(request.url.params.multi_items()) == sorted(
            [("access_token", TOKEN), ("page", "2"), ("per_page", "100")]
        )
        assert not request.content and request.headers["accept"] == "application/json"
        assert "private-token" not in request.headers and "authorization" not in request.headers
        headers = {"location": f"{ORIGIN}/unexpected"} if status == 302 else {}
        return httpx.Response(status, headers=headers, json=[] if status == 200 else {"message": "not available"})

    route = strict_http.get(ORIGIN + PATH).mock(side_effect=response)
    if status == 200:
        assert service.replies_page(8, "comment-雪", page=2, per_page=100) == []
    else:
        with pytest.raises(APIError) as exc:
            service.replies_page(8, "comment-雪", page=2, per_page=100)
        assert exc.value.status_code == status
    assert route.call_count == 1


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
