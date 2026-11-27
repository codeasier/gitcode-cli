import json
from copy import deepcopy

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

INLINE = "gitcode_add_pull_request_inline_comment"
REPLY = "gitcode_reply_to_pull_request_discussion"
BASE = {"owner": "allowed", "repo": "project", "pull_number": 7, "body": "line note"}
SHA = "ad" * 20
DID = "thread-id-3"
SCOPE = "/api/v5/repos/allowed/project/pulls/7"
INLINE_ARGS = {**BASE, "path": "src/树.py", "position": 18, "expected_head_sha": SHA.upper()}
REPLY_ARGS = {**BASE, "discussion_id": DID, "page": 2, "per_page": 20}
PR = {"number": 7, "head": {"sha": SHA}}
HUNK = {"line_content": "@@ -11,2 +17,2 @@", "type": "match", "old_line": "...", "new_line": "..."}
DIFF = {
    "code": 0,
    "count": 1,
    "diff_refs": {"head_sha": SHA},
    "diffs": [
        {
            "statistic": {
                "type": "text_type",
                "path": INLINE_ARGS["path"],
                "new_path": INLINE_ARGS["path"],
            },
            "head": {"commit_id": SHA},
            "added_lines": 1,
            "remove_lines": 1,
            "content": {
                "text": [
                    HUNK,
                    {
                        "line_content": " context",
                        "old_line": {"line_num": 11},
                        "new_line": {"line_num": 17},
                    },
                    {
                        "line_content": "-old",
                        "type": "old",
                        "old_line": {"line_num": 12},
                        "new_line": {"line_num": ""},
                    },
                    {
                        "line_content": "+new",
                        "type": "new",
                        "old_line": {"line_num": ""},
                        "new_line": {"line_num": 18},
                    },
                ]
            },
        }
    ],
}
ROWS = [{"id": 123, "discussion_id": DID}]
NOTE = {"id": DID, "body": BASE["body"]}
REPLY_NOTE = {**NOTE, "noteId": 456}


def run(tool, args, responses, *, allowed=("allowed/project",), read_only=False):
    requests = []

    def handle(request):
        requests.append(request)
        index = len(requests) - 1
        assert index < len(responses), "unexpected request"
        assert request.url.scheme == "https" and request.url.host == "api.gitcode.com"
        assert request.headers["authorization"] == "Bearer dummy-review-token"
        assert "private-token" not in request.headers
        assert "access_token" not in request.url.params
        if isinstance(responses[index], Exception):
            raise responses[index]
        return httpx.Response(200, json=responses[index])

    with GitCodeAPI("dummy-review-token", transport=httpx.MockTransport(handle)) as api:
        catalog = GitCodeTools(api, allowed_repositories=allowed, read_only=read_only)
        try:
            result = catalog.call(tool, args)
        except GitCodeError as error:
            result = error
        return result, requests


def test_inline_publishes_one_native_write_without_sha_or_side():
    result, requests = run(INLINE, INLINE_ARGS, [PR, DIFF, NOTE])
    assert [r.method for r in requests] == ["GET", "GET", "POST"]
    assert [r.url.path for r in requests] == [SCOPE, SCOPE + "/files.json", SCOPE + "/comments"]
    assert json.loads(requests[-1].content) == {
        "body": BASE["body"],
        "path": "src/树.py",
        "position": 18,
    }
    assert result == {
        "repository": "allowed/project",
        "data": {"id": DID, "observed_head_sha": SHA, "placement_verified": False},
    }


@pytest.mark.parametrize("overrides", [{"path": "missing.py"}, {"position": 12}, {"position": 19}])
def test_inline_rejects_missing_path_left_only_line_and_line_outside_hunks(overrides):
    error, requests = run(INLINE, {**INLINE_ARGS, **overrides}, [PR, DIFF])
    assert error.code == "diff_anchor_not_verified"
    assert [r.method for r in requests] == ["GET", "GET"]


def test_right_side_context_line_is_a_valid_anchor():
    result, requests = run(INLINE, {**INLINE_ARGS, "position": 17}, [PR, DIFF, NOTE])
    assert result["data"]["observed_head_sha"] == SHA
    assert json.loads(requests[-1].content)["position"] == 17


@pytest.mark.parametrize(
    "transform,code",
    [
        (lambda d, f, r: d.update(truncated=True), "invalid_response"),
        (lambda d, f, r: d.update(code=False), "invalid_response"),
        (lambda d, f, r: d.update(count=2), "invalid_response"),
        (lambda d, f, r: d.update(diff_refs={}), "invalid_response"),
        (lambda d, f, r: d.update(diff_refs={"head_sha": "ef" * 20}), "conflict"),
        (
            lambda d, f, r: d["diffs"].append({"statistic": {}}) or d.update(count=2),
            "invalid_response",
        ),
        (lambda d, f, r: d["diffs"].append(f) or d.update(count=2), "diff_anchor_not_verified"),
        (lambda d, f, r: f["head"].update(commit_id="ef" * 20), "diff_anchor_not_verified"),
        (lambda d, f, r: f["statistic"].update(type="image_type"), "diff_anchor_not_verified"),
        (lambda d, f, r: f["statistic"].update(path="old-name.py"), "diff_anchor_not_verified"),
        (lambda d, f, r: f.update(content=None), "diff_anchor_not_verified"),
        (lambda d, f, r: f["content"].update(too_large=1), "diff_anchor_not_verified"),
        (lambda d, f, r: f.update(added_lines=2), "diff_anchor_not_verified"),
        (lambda d, f, r: r.pop(1), "diff_anchor_not_verified"),
        (lambda d, f, r: r.append(r[-1]), "diff_anchor_not_verified"),
        (lambda d, f, r: r[-1]["new_line"].update(line_num="18"), "diff_anchor_not_verified"),
        (lambda d, f, r: r[-1].update(type="old"), "diff_anchor_not_verified"),
        (lambda d, f, r: r[0].update(line_content="an omitted hunk"), "diff_anchor_not_verified"),
    ],
)
def test_inline_ambiguity_malformed_or_truncated_diff_never_posts(transform, code):
    diff = deepcopy(DIFF)
    target = diff["diffs"][0]
    transform(diff, target, target["content"]["text"])
    error, requests = run(INLINE, INLINE_ARGS, [PR, diff])
    assert error.code == code
    assert [r.method for r in requests] == ["GET", "GET"]


@pytest.mark.parametrize(
    "note_ids", [{"noteId": 456}, {"note_id": 456}, {"noteId": 456, "note_id": 456}]
)
def test_reply_reads_exact_prs_selected_page_before_one_post(note_ids):
    result, requests = run(REPLY, REPLY_ARGS, [ROWS, {**NOTE, **note_ids}])
    assert [r.method for r in requests] == ["GET", "POST"]
    assert [r.url.path for r in requests] == [
        SCOPE + "/comments",
        SCOPE + f"/discussions/{DID}/comments",
    ]
    assert dict(requests[0].url.params) == {"page": "2", "per_page": "20"}
    assert not requests[1].url.params
    assert json.loads(requests[1].content) == {"body": BASE["body"]}
    assert result["data"] == {"discussion_id": DID, "note_id": 456}


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"noteId": 1, "note_id": 2},
        {"noteId": 1, "note_id": True},
        {"noteId": True, "note_id": 1},
        {"noteId": 1, "note_id": 1.0},
        {"noteId": None, "note_id": 1},
        {"noteId": 1, "note_id": None},
        {"note_id": "1"},
        {"note_id": 0},
        {"note_id": -1},
        {"note_id": True},
        {"note_id": 1, "body": "different"},
        {"note_id": 1, "id": "different"},
    ],
)
def test_invalid_reply_receipt_is_uncertain_after_one_write(fields):
    error, requests = run(REPLY, REPLY_ARGS, [ROWS, {**NOTE, **fields}])
    assert isinstance(error, GitCodeError)
    assert error.code == "invalid_response" and error.operation_may_have_completed
    assert [r.method for r in requests] == ["GET", "POST"]


@pytest.mark.parametrize(
    "head",
    [
        {"number": 7, "head": {"sha": "c" * 40}},
        {"number": 8, "head": {"sha": SHA}},
        {"number": 7, "head": {}},
        None,
    ],
)
def test_head_preflight_stops_without_a_write(head):
    result, requests = run(INLINE, INLINE_ARGS, [head])
    assert isinstance(result, GitCodeError)
    assert result.code in {"conflict", "invalid_response"}
    assert [r.method for r in requests] == ["GET"]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"id": DID}],
        [{"discussion_id": "wrong"}],
        [{"reply": [{"discussion_id": DID}]}],
        [None],
        [{}] * 21,
        {"discussion_id": DID},
    ],
)
def test_no_blind_replies_to_unverified_discussions(rows):
    result, requests = run(REPLY, REPLY_ARGS, [rows])
    assert isinstance(result, GitCodeError)
    assert result.code in {"invalid_response", "discussion_not_verified"}
    assert [r.method for r in requests] == ["GET"]


@pytest.mark.parametrize("tool,args", [(INLINE, INLINE_ARGS), (REPLY, REPLY_ARGS)])
def test_policy_is_checked_before_any_read_or_write(tool, args):
    result, requests = run(tool, args, [], read_only=True)
    assert result.code == "read_only" and requests == []
    result, requests = run(tool, args, [], allowed=("other/repo",))
    assert result.code == "repository_not_allowed" and requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"position": False},
        {"position": 0},
        {"position": -1},
        {"position": 3.2},
        {"path": "../x"},
        {"path": "a%2Fb"},
        {"expected_head_sha": "main"},
        {"body": " "},
        {"body": "\u0000"},
        {"side": "LEFT"},
        {"commit_id": SHA},
    ],
)
def test_invalid_inline_arguments_do_not_touch_the_network(overrides):
    error, requests = run(INLINE, {**INLINE_ARGS, **overrides}, [])
    assert error.code == "invalid_arguments" and requests == []


@pytest.mark.parametrize(
    "overrides",
    [{"discussion_id": x} for x in [".", "..", "/x", "x%2fy", "x?", "x#", "x\n", True, "a" * 129]]
    + [{"page": False}, {"per_page": 101}, {"body": "  "}],
)
def test_invalid_reply_arguments_do_not_touch_the_network(overrides):
    error, requests = run(REPLY, {**REPLY_ARGS, **overrides}, [])
    assert error.code == "invalid_arguments" and requests == []


@pytest.mark.parametrize(
    "tool,args,results",
    [
        (INLINE, INLINE_ARGS, [PR, DIFF, {}]),
        (INLINE, INLINE_ARGS, [PR, DIFF, {**NOTE, "id": False}]),
        (INLINE, INLINE_ARGS, [PR, DIFF, {**NOTE, "body": "different"}]),
        (REPLY, REPLY_ARGS, [ROWS, {**REPLY_NOTE, "id": "different"}]),
        (REPLY, REPLY_ARGS, [ROWS, {**REPLY_NOTE, "noteId": True}]),
        (REPLY, REPLY_ARGS, [ROWS, None]),
        (REPLY, REPLY_ARGS, [ROWS, httpx.ReadTimeout("private-response")]),
    ],
)
def test_ambiguous_write_is_not_retried_and_does_not_leak_response(tool, args, results):
    error, requests = run(tool, args, results)
    assert isinstance(error, GitCodeError) and error.operation_may_have_completed
    expected_methods = ["GET", "GET", "POST"] if tool == INLINE else ["GET", "POST"]
    assert [r.method for r in requests] == expected_methods
    assert "private-response" not in error.message


def test_catalog_marks_both_tools_as_writes():
    with GitCodeAPI("") as api:
        catalog = {t.name: t for t in GitCodeTools(api).list_tools()}
        for name in (INLINE, REPLY):
            assert catalog[name].annotations.model_dump(by_alias=True)["readOnlyHint"] is False
        assert {INLINE, REPLY}.isdisjoint(
            t.name for t in GitCodeTools(api, read_only=True).list_tools()
        )


@pytest.mark.anyio
async def test_review_writes_via_mcp_protocol(anyio_backend):
    from mcp.client import Client

    from gitcode_mcp.config import Settings
    from gitcode_mcp.server import create_server

    seen = []
    answers = iter([PR, DIFF, NOTE, ROWS, {**NOTE, "note_id": 456}])

    def handle(request):
        seen.append(request.method)
        return httpx.Response(200, json=next(answers))

    with GitCodeAPI("dummy-review-token", transport=httpx.MockTransport(handle)) as api:
        async with Client(
            create_server(Settings(allowed_repositories=("allowed/project",)), api=api)
        ) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert {INLINE, REPLY} <= names
            for tool, args in ((INLINE, INLINE_ARGS), (REPLY, REPLY_ARGS)):
                response = await client.call_tool(tool, args)
                assert (
                    not response.is_error
                    and response.structured_content["repository"] == "allowed/project"
                )
                if tool == REPLY:
                    assert response.structured_content["data"] == {
                        "discussion_id": DID,
                        "note_id": 456,
                    }
    assert seen == ["GET", "GET", "POST", "GET", "POST"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
