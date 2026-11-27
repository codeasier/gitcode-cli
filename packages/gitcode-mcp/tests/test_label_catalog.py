import json

import httpx
import pytest
from mcp.client import Client

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.config import Settings
from gitcode_mcp.server import create_server
from gitcode_mcp.tools import GitCodeTools

TOKEN = "synthetic-label-fixture"
REPO = {"owner": "Team", "repo": "r"}
BASE = "https://api.gitcode.com/api/v5/repos/Team/r/labels"
TOOL = "gitcode_list_labels"


def row(identity, **fields):
    return {"id": identity, "name": f"label-{identity}", "repository_id": 7, **fields}


def make_api(responses, *, max_bytes=2_000_000, token=TOKEN):
    requests = []

    def handle(request):
        requests.append(request)
        number = int(request.url.params["page"])
        assert request.method == "GET"
        assert str(request.url).split("?", 1)[0] == BASE
        assert dict(request.url.params) == {"page": str(number), "per_page": "100"}
        assert request.headers["Authorization"] == f"Bearer {token}"
        assert request.headers["Accept-Encoding"] == "identity"
        assert not {"private-token", "cookie"} & set(request.headers)
        assert not request.content
        response = responses[number - 1]
        return (
            response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
        )

    return GitCodeAPI(
        token, max_response_bytes=max_bytes, transport=httpx.MockTransport(handle)
    ), requests


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_native_pages_are_verified_before_serving_exact_local_pages_over_protocol():
    rows = [row(i, extra={"native": True}) for i in range(1, 264)]
    rows[1]["name"], rows[101]["name"] = "Bug", "bug"
    pages = [
        httpx.Response(
            200,
            json=rows[:100],
            headers={
                "X-Total": "263",
                "X-Total-Pages": "3",
                "X-Next-Page": "2",
                "Set-Cookie": "sid=discard-me; Path=/",
                "Link": f'<{BASE}?per_page=100&page=2>; rel="next", <?per_page=100&page=3>; rel=last',
            },
        ),
        rows[100:200],
        httpx.Response(
            200,
            json=rows[200:],
            headers={
                "X-Page": "3",
                "X-Per-Page": "100",
                "X-Next-Page": "",
                "Link": "</api/v5/repos/Team/r/labels?page=2&per_page=100>; rel=prev",
            },
        ),
        [],
    ]
    api, requests = make_api(pages)
    with api:
        async with Client(
            create_server(Settings(read_only=True, allowed_repositories=("Team/r",)), api=api)
        ) as client:
            for page, size, expected_next in [
                (1, 30, 2),
                (2, 75, 3),
                (3, 100, None),
                (10, 30, None),
            ]:
                result = await client.call_tool(TOOL, {**REPO, "page": page, "per_page": size})
                assert not result.is_error
                body = result.structured_content
                assert json.loads(result.content[0].text) == body
                assert body["repository"] == "Team/r"
                assert (body["page"], body["per_page"], body["total_items"], body["next_page"]) == (
                    page,
                    size,
                    263,
                    expected_next,
                )
                assert body["data"] == rows[(page - 1) * size : page * size]
                assert body["pagination_mode"] == "client"
                assert "not a stable snapshot" in body["pagination_note"]
    assert [r.url.params["page"] for r in requests] == ["1", "2", "3", "4"] * 4


def call(pages, **api_opts):
    api, requests = make_api(pages, **api_opts)
    with api:
        result = GitCodeTools(api).call(TOOL, {**REPO, "page": 1, "per_page": 1})
    return result, len(requests)


@pytest.mark.parametrize(
    "headers",
    [
        {"Link": '<?page=3&per_page=100>; rel="next"'},
        {"Link": '<?page=3&per_page=33>; rel="last"'},
        {"Link": "<?page=1&page=2&per_page=100>; rel=next"},
        {"Link": "<https://unrelated.test/?page=2&per_page=100>; rel=next"},
        {"Link": "</api/v5/repos/Team/other/labels?page=2&per_page=100>; rel=next"},
        {"Link": "<?page=2&per_page=100>; rel=next, <?page=2&per_page=100>; rel=next"},
        {"Link": "<?page=2&per_page=100>; rel=next", "X-Next-Page": ""},
        {"Link": "<?page=2&per_page=100>; rel=next, <?page=1&per_page=100>; rel=last"},
        {"Link": "<?page=2&per_page=100>; rel=last", "X-Total-Pages": "1"},
        {"X-Page": "2"},
        {"X-Per-Page": "30"},
        {"X-Prev-Page": "5"},
        {"X-Total": "00"},
        {"X-Total-Pages": "11"},
        {"X-Total": "1001"},
        {"X-Truncated": "true"},
        {"X-Incomplete-Results": "1"},
        {"Content-Range": "labels 1-5/100"},
        [("X-Total", "1"), ("X-Total", "1")],
    ],
)
def test_conflicting_or_unbounded_native_evidence_fails_closed(headers):
    with pytest.raises(GitCodeError) as exc:
        call([httpx.Response(200, json=[row(1)], headers=headers)])
    assert exc.value.code == "invalid_response"


@pytest.mark.parametrize(
    "bad",
    [
        [row(1)],
        [row(2, name="label-1")],
        [row(2, repository_id=8)],
        [{"name": "missing"}],
        [row(True)],
        [row(2, name="")],
        [row(2, repository_id=True)],
        [row(2)] * 101,
        httpx.Response(200, json=[], headers={"X-Next-Page": "3"}),
        httpx.Response(200, json=[], headers={"X-Total": "7"}),
        httpx.Response(200, json=[], headers={"X-Total-Pages": "3"}),
        httpx.Response(206, json=[]),
        httpx.Response(200, content=b"[]"),
        httpx.Response(
            200, content=b'[{"id":2,"id":3}]', headers={"Content-Type": "application/json"}
        ),
        httpx.Response(200, json={"labels": []}),
    ],
)
def test_invalid_later_page_cannot_return_requested_first_row(bad):
    with pytest.raises(GitCodeError) as exc:
        call([[row(1)], bad])
    assert exc.value.code == "invalid_response"


@pytest.mark.parametrize(
    ("first_claim", "second"),
    [
        ({"X-Total": "1"}, [row(2)]),
        ({"X-Next-Page": ""}, [row(2)]),
        ({"X-Next-Page": "2"}, []),
        ({"X-Total-Pages": "1"}, [row(2)]),
        ({"X-Total": "1"}, httpx.Response(200, json=[], headers={"X-Total": "2"})),
        ({"Link": "<?page=2&per_page=100>; rel=last"}, []),
    ],
)
def test_reconcile_claims_across_pages(first_claim, second):
    with pytest.raises(GitCodeError, match="complete repository label"):
        call([httpx.Response(200, json=[row(1)], headers=first_claim), second])


def test_empty_and_bounds():
    result, count = call([[]])
    assert (
        count == 1
        and result["data"] == []
        and result["next_page"] is None
        and result["total_items"] == 0
    )
    pages = [[row(i + j + 1) for j in range(100)] for i in range(0, 1000, 100)]
    result, count = call([*pages, []])
    assert count == 11 and result["total_items"] == 1000 and result["data"] == [row(1)]
    with pytest.raises(GitCodeError, match="complete repository label"):
        call([*pages, [row(1001)]])
    with pytest.raises(GitCodeError) as exc:
        call([[row(1)], [row(2)]], max_bytes=60)
    assert exc.value.code == "response_too_large"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.Response(302, headers={"Location": "https://unrelated.test/"}), "upstream_redirect"),
        (httpx.Response(403, json={"detail": TOKEN}), "permission_denied"),
        (httpx.Response(429, headers={"Retry-After": "30"}), "rate_limited"),
    ],
)
def test_later_denial_never_returns_partial_data_or_retries(failure, code):
    api, requests = make_api([[row(1)], failure])
    with api, pytest.raises(GitCodeError) as exc:
        GitCodeTools(api).call(TOOL, REPO)
    assert exc.value.code == code and TOKEN not in str(exc.value)
    assert len(requests) == 2


def test_allowlist_and_missing_credentials_are_checked_before_io():
    api, requests = make_api([], token="")
    with api:
        with pytest.raises(GitCodeError) as exc:
            GitCodeTools(api).call(TOOL, REPO)
        assert exc.value.code == "configuration_error"
        with pytest.raises(GitCodeError) as exc:
            GitCodeTools(api, allowed_repositories=("Other/r",)).call(TOOL, REPO)
        assert exc.value.code == "repository_not_allowed"
    assert requests == []


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({"X-Filler": "x" * 32768}, "response_too_large"),
        ([(f"x-{i}", "1") for i in range(128)], "response_too_large"),
        ({"Content-Length": "1"}, "invalid_response"),
        ([("Content-Length", "2"), ("Content-Length", "2")], "invalid_response"),
        (
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Type", "text/html")],
            "invalid_response",
        ),
        ({"Content-Encoding": "x-unsupported"}, "invalid_response"),
    ],
)
def test_label_page_response_header_bound_and_consistency(headers, code):
    with pytest.raises(GitCodeError) as exc:
        call([httpx.Response(200, json=[], headers=headers)])
    assert exc.value.code == code
