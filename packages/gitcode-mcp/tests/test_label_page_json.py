"""List-label native JSON is safe to return unchanged as an MCP result."""

import json
import math

import anyio
import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

NAME = "gitcode_list_labels"
REPO = {"owner": "Team", "repo": "r"}
PATH = "/repos/Team/r/labels"
TOKEN = "fixture-page-secret"


def wire(body):
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def catalog_call(responses, *, asynchronous):
    seen = []

    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "api.gitcode.com"
        assert request.url.path == "/api/v5" + PATH
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers
        assert dict(request.url.params) == {"page": str(len(seen) + 1), "per_page": "100"}
        seen.append(request.url.params["page"])
        return wire(responses[len(seen) - 1])

    def read():
        with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
            tools = GitCodeTools(api, allowed_repositories=("Team/r",))
            if asynchronous:
                return anyio.run(tools.call_label_catalog, REPO)
            return tools.call(NAME, REPO)

    return read, seen


@pytest.mark.parametrize("asynchronous", (False, True), ids=("sync", "async"))
@pytest.mark.parametrize(
    "bad_page",
    (
        b'[{"id":2,"name":"two","native":{"float":NaN}}]',
        b'[{"id":2,"name":"two","native":[Infinity]}]',
        b'[{"id":2,"name":"two","native":[-Infinity]}]',
        b'[{"id":2,"name":"two","native":[1e400]}]',
        b'[{"id":2,"name":"two","native":[-1e400]}]',
        rb'[{"id":2,"name":"two","native":["\ud800"]}]',
        rb'[{"id":2,"name":"two","native":{"\udfff":null}}]',
        rb'[{"id":2,"name":"two","native":{"same":1,"\u0073ame":2}}]',
        rb'[{"id":2,"name":"two","name":"other"}]',
        b'[{"id":2,"name":"two","native":"\xff"}]',
        '[{"id":2,"name":"two"}]'.encode("utf-16"),
        b'\xef\xbb\xbf[{"id":2,"name":"two"}]',
    ),
    ids=(
        "nan",
        "pos-infinity",
        "neg-infinity",
        "pos-overflow",
        "neg-overflow",
        "surrogate-value",
        "surrogate-key",
        "duplicate-key-escaped",
        "duplicate-row-field",
        "non-utf8",
        "utf16",
        "utf8-bom",
    ),
)
def test_bad_later_page_has_sanitized_error_and_no_partial_result(asynchronous, bad_page):
    call, seen = catalog_call(
        [b'[{"id":1,"name":"one"}]', bad_page, b"[]"], asynchronous=asynchronous
    )
    with pytest.raises(GitCodeError) as error:
        call()
    assert error.value.to_dict() == {
        "code": "invalid_response",
        "message": "GitCode returned an invalid JSON page.",
    }
    assert seen == ["1", "2"]


@pytest.mark.parametrize("asynchronous", (False, True), ids=("sync", "async"))
def test_valid_unicode_and_mixed_native_types_roundtrip_as_utf8(asynchronous):
    page = (
        '[{"id":1,"name":"中文","native":{"é":'
        '["日本語","\\ud83d\\ude80",{"\\ud83d\\ude80":true,"f":1.25e2,"n":null},3,false]}}]'
    ).encode()
    call, seen = catalog_call([page, b"[]"], asynchronous=asynchronous)
    result = call()
    assert seen == ["1", "2"]
    assert result["total_items"] == 1
    assert result["data"] == [
        {
            "id": 1,
            "name": "中文",
            "native": {"é": ["日本語", "🚀", {"🚀": True, "f": 125.0, "n": None}, 3, False]},
        }
    ]
    # MCP uses both a UTF-8 text result and structured JSON.
    assert json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) == result


def test_decoder_does_not_change_other_api_reads_or_task_label_mutation_wire():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return wire(b'{"legacy":NaN}')
        return wire(b'{"id":1,"name":"fixture-created"}')

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        assert math.isnan(api.request("GET", "/repos/Team/r")["legacy"])
        data, _ = api.task_label_request(
            "POST", PATH, form={"name": "fixture-created", "color": "#123456"}
        )
    assert data == {"id": 1, "name": "fixture-created"}
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/api/v5/repos/Team/r"),
        ("POST", "/api/v5" + PATH),
    ]
    post = requests[-1]
    assert not post.url.query
    assert post.headers["authorization"] == "Bearer " + TOKEN
    assert post.headers["content-type"] == "application/x-www-form-urlencoded"
    assert post.content == b"name=fixture-created&color=%23123456"
