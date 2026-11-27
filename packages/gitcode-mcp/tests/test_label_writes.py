"""Task label writes via the catalog and MCP's bounded bearer-only HTTP transport."""

import json
from contextlib import contextmanager
from urllib.parse import parse_qs

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

REPO = {"owner": "team", "repo": "project"}
TOKEN = "test-only-credential"
OLD = {"name": "旧 标签", "id": 24, "color": "#FFEEDD", "repository_id": 800}
ARGS = {
    "create": {"name": "新 名", "color": "aabbcc"},
    "update": {"name": OLD["name"], "expected_id": 24, "new_name": "新 名", "color": "aabbcc"},
    "delete": {"name": OLD["name"], "expected_id": 24},
}


@contextmanager
def harness(responses, **settings):
    requests = []

    def handler(req):
        requests.append(req)
        assert (
            req.url.host == "api.gitcode.com" and req.headers["Authorization"] == "Bearer " + TOKEN
        )
        assert TOKEN not in str(req.url) and TOKEN not in req.content.decode()
        assert "private-token" not in req.headers
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, httpx.Response) else httpx.Response(200, json=item)

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        yield GitCodeTools(api, **settings), requests


def call(tools, operation, args=None):
    return tools.call(
        f"gitcode_{operation}_label", {**REPO, **(ARGS[operation] if args is None else args)}
    )


def test_create_form_once_with_minimal_matching_receipt():
    with harness([{"id": 45, "name": "新 名", "color": "#aabbcc", "surplus": TOKEN}]) as (
        tools,
        requests,
    ):
        assert call(tools, "create") == {
            "repository": "team/project",
            "data": {
                "id": 45,
                "name": "新 名",
                "color": "#aabbcc",
                "verification": "mutation_receipt",
            },
        }
    (req,) = requests
    assert (
        req.method == "POST"
        and req.url.path == "/api/v5/repos/team/project/labels"
        and not req.url.query
    )
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(req.content.decode()) == {"name": ["新 名"], "color": ["#AABBCC"]}


def test_update_uses_numbered_preflight_and_documented_query_not_json():
    updated = {**OLD, "name": "新 名", "color": "#aabbcc"}
    with harness([[OLD], [], updated]) as (tools, requests):
        assert call(tools, "update")["data"]["id"] == OLD["id"]
    assert [r.method for r in requests] == ["GET", "GET", "PATCH"]
    assert [dict(r.url.params) for r in requests[:2]] == [
        {"page": str(i), "per_page": "100"} for i in (1, 2)
    ]
    assert requests[-1].url.raw_path.startswith(
        b"/api/v5/repos/team/project/labels/%E6%97%A7%20%E6%A0%87%E7%AD%BE?"
    )
    assert (
        dict(requests[-1].url.params) == {"name": "新 名", "color": "#AABBCC"}
        and not requests[-1].content
    )


@pytest.mark.parametrize("status", [200, 204])
def test_delete_requires_empty_terminal_page_and_readback_even_after_short_page(status):
    other = {**OLD, "id": 26, "name": "another"}
    with harness([[other], [OLD], [], httpx.Response(status), [other], []]) as (tools, requests):
        assert call(tools, "delete")["data"] == {
            "id": 24,
            "name": "旧 标签",
            "readback": "absent_from_observed_catalog",
        }
    assert [r.method for r in requests] == ["GET", "GET", "GET", "DELETE", "GET", "GET"]


@pytest.mark.parametrize("op", ["create", "update", "delete"])
def test_write_only_tool_visibility_access_and_allowlist(op):
    with harness([], read_only=True) as (tools, requests):
        assert f"gitcode_{op}_label" not in {t.name for t in tools.list_tools()}
        with pytest.raises(GitCodeError, match="read-only") as e:
            call(tools, op)
        assert e.value.code == "read_only" and not requests
    with harness([], allowed_repositories=["other/project"]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, op)
        assert e.value.code == "repository_not_allowed" and not requests


@pytest.mark.parametrize(
    ("op", "override"),
    [
        ("create", {"color": "#AABB\n"}),
        ("create", {"name": "../labels"}),
        ("create", {"name": "tag,foo"}),
        ("create", {"name": "name%2fetc"}),
        ("create", {"name": "foo\ud800"}),
        ("create", {"force": True}),
        ("delete", {"expected_id": True}),
        ("update", {"new_name": None, "color": None}),
        ("update", {"new_name": TOKEN}),
        ("delete", {"name": "foo?bar"}),
    ],
)
def test_invalid_arguments_are_offline(op, override):
    with harness([]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, op, {**ARGS[op], **override})
        assert e.value.code == "invalid_arguments" and not requests and TOKEN not in str(e.value)


@pytest.mark.parametrize("op", ["update", "delete"])
@pytest.mark.parametrize(
    "pre",
    [
        [{**OLD, "id": 44}],
        [{**OLD, "name": "other"}],
        [OLD, {**OLD, "id": 56}],
        [{**OLD, "id": True}],
    ],
)
def test_precondition_failure_makes_no_write(op, pre):
    with harness([pre, []]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, op)
        assert (
            e.value.code in {"conflict", "invalid_response"}
            and not e.value.operation_may_have_completed
        )
        assert all(req.method == "GET" for req in requests)


@pytest.mark.parametrize(
    "receipt",
    [
        {},
        {"id": True, "name": "新 名", "color": "#AABBCC"},
        {"id": 3, "name": "新 名", "color": "#AABBCC"},
        {"id": 24, "name": "wrong", "color": "#AABBCC"},
        httpx.Response(202, json=OLD),
        httpx.Response(500, json=OLD),
    ],
)
def test_update_never_replays_ambiguous_responses(receipt):
    with harness([[OLD], [], receipt]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, "update")
        assert (
            e.value.operation_may_have_completed and sum(r.method == "PATCH" for r in requests) == 1
        )


@pytest.mark.parametrize(
    "bad",
    [
        [OLD],
        [{**OLD, "name": "other"}],
        [{**OLD, "id": 8}],
        httpx.Response(403, json={"body": TOKEN}),
        httpx.Response(200, json=[], headers={"X-Total": "9"}),
        httpx.Response(200, json=[], headers={"Link": '<https://example.invalid/>; rel="next"'}),
        httpx.Response(200, json=[{}]),
    ],
)
def test_delete_readback_failures_preserve_uncertainty_without_replaying(bad):
    with harness([[OLD], [], httpx.Response(200), bad, []]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, "delete")
        assert e.value.operation_may_have_completed and TOKEN not in json.dumps(e.value.to_dict())
        assert sum(r.method == "DELETE" for r in requests) == 1


def test_protocol_create_update_delete_and_cookie_free_readback():
    from starlette.testclient import TestClient

    from gitcode_mcp.config import Settings
    from gitcode_mcp.server import create_http_app, create_server

    current = {}
    methods = []

    def upstream(req):
        methods.append(req.method)
        assert req.headers.get("authorization") == "Bearer " + TOKEN
        assert "cookie" not in req.headers
        if req.method == "GET":
            result = list(current.values()) if req.url.params["page"] == "1" else []
        elif req.method == "POST":
            form = parse_qs(req.content.decode())
            name = form["name"][0]
            result = current[24] = {"id": 24, "name": name, "color": form["color"][0]}
        elif req.method == "PATCH":
            assert req.url.path.endswith("/初 始")
            current[24].update(dict(req.url.params))
            result = current[24]
        else:
            assert req.url.path.endswith("/新 名")
            del current[24]
            result = {}
        return httpx.Response(200, json=result, headers={"Set-Cookie": "unexpected=synthetic"})

    settings = Settings(allowed_repositories=("team/project",), http_token="transport-token")
    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(upstream)) as api:
        app = create_http_app(create_server(settings, api=api), settings)
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:

            def rpc(method, params=None):
                body = {"jsonrpc": "2.0", "id": 1, "method": method}
                if params is not None:
                    body["params"] = params
                res = client.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer transport-token",
                    },
                    json=body,
                )
                assert res.status_code == 200
                return res.json()["result"]

            listing = {row["name"]: row for row in rpc("tools/list")["tools"]}
            for op in ("create", "update", "delete"):
                hints = listing[f"gitcode_{op}_label"]["annotations"]
                assert hints["readOnlyHint"] is False
                assert hints["destructiveHint"] is (op != "create")
            for op, args in (
                ("create", {"name": "初 始", "color": "affe00"}),
                ("update", {"name": "初 始", "expected_id": 24, "new_name": "新 名"}),
                ("delete", {"name": "新 名", "expected_id": 24}),
            ):
                receipt = rpc(
                    "tools/call", {"name": f"gitcode_{op}_label", "arguments": {**REPO, **args}}
                )
                assert not receipt["isError"] and receipt["structuredContent"]["data"]["id"] == 24
    assert methods == ["POST", "GET", "GET", "PATCH", "GET", "GET", "DELETE", "GET"]


def test_wrong_method_route_and_form_shape_offline():
    with GitCodeAPI(
        TOKEN, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected network"))
    ) as api:
        for method, path, args in [
            ("POST", "/repos/team/project/issues", {"form": {"name": "n", "color": "#aaa"}}),
            ("PATCH", "/repos/team/project/labels", {"params": {"name": "n"}}),
            (
                "POST",
                "/repos/team/project/labels",
                {"form": {"name": "n", "color": "#aaa", "access_token": "x"}},
            ),
        ]:
            with pytest.raises(GitCodeError) as e:
                api.task_label_request(method, path, **args)
            assert e.value.code == "invalid_arguments"


@pytest.mark.parametrize(
    "header",
    [
        {
            "Link": '<https://api.gitcode.com/api/v5/repos/team/other/labels?page=2&per_page=100>; rel="next"'
        },
        {"X-Total": "0"},
        {"X-Total-Pages": "1", "X-Next-Page": "2"},
        {"X-Per-Page": "1"},
        {"X-Incomplete-Results": "true"},
        {"Content-Range": "items 0-99/1000"},
    ],
)
def test_incoherent_preflight_header_rejects_without_mutation(header):
    with harness([httpx.Response(200, json=[OLD], headers=header), []]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, "delete")
        assert e.value.code == "invalid_response"
        assert all(q.method == "GET" for q in requests)


def test_rejected_asynchronous_delete_does_not_report_success_or_replay():
    with harness([[OLD], [], httpx.Response(202, json={})]) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, "delete")
        assert e.value.operation_may_have_completed and len(requests) == 3


def test_catalog_bounds_for_sparse_pages_and_encoded_source_name():
    rows = [[OLD]] + [[{**OLD, "id": 100 + i, "name": f"row-{i}"}] for i in range(10)]
    with harness(rows) as (tools, requests):
        with pytest.raises(GitCodeError) as e:
            call(tools, "update")
        assert e.value.code == "invalid_response"
        assert len(requests) == 11 and all(q.method == "GET" for q in requests)


@pytest.mark.parametrize("op", ["create", "update"])
def test_empty_200_is_not_a_create_or_update_receipt(op):
    preflight = [[OLD], []] if op == "update" else []
    with harness([*preflight, httpx.Response(200)]) as (tools, requests):
        with pytest.raises(GitCodeError) as error:
            call(tools, op)
        assert error.value.code == "invalid_response"
        assert error.value.operation_may_have_completed
        assert sum(request.method in {"POST", "PATCH"} for request in requests) == 1
