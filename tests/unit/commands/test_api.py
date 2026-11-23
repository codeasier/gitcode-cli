"""Mock-transport contracts; no network, real tokens, or remote mutations."""

from __future__ import annotations

import json
import shutil
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import rest_api
from gitcode_cli.cli import main
from gitcode_cli.commands import api

TOKEN = "synthetic-test-only-token"


@pytest.fixture
def call(monkeypatch, tmp_config_dir):
    monkeypatch.setitem(main.commands, "api", api.api_command)
    requests = []

    def invoke(args, replies=(), *, token=TOKEN, stdin=None, repo=None, separate_stderr=False):
        def handler(request):
            index = len(requests)
            requests.append(request)
            if index >= len(replies):
                pytest.fail("Unexpected HTTP request")
            response = replies[index]
            if isinstance(response, Exception):
                raise response
            return response

        requests.clear()
        monkeypatch.setattr(rest_api, "open_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        root = ["-R", repo] if repo else []
        # Click 8.1 merges stderr into Result.stdout unless explicitly separated;
        # Click 8.2+ always captures the individual streams.
        opts = {"mix_stderr": False} if separate_stderr and "mix_stderr" in signature(CliRunner).parameters else {}
        return CliRunner(**opts).invoke(main, [*root, "api", *args], input=stdin, env={"GC_TOKEN": token})

    return invoke, requests


def test_get_version_placeholders_and_headers(call):
    invoke, requests = call
    response = httpx.Response(
        200,
        headers={"ETag": "abc", "Set-Cookie": "session=not-for-output"},
        json={"title": "宝石", "nested": [{"secret": "private"}, TOKEN]},
    )
    result = invoke(
        ["/api/v8/repos/{owner}/{repo}/actions/runs?branch=a%2Fb", "-i", "-H", "If-None-Match: old"],
        [response],
        repo="gitcode.com/Acme/tools",
    )
    assert result.exit_code == 0, result.output
    assert "HTTP 200" in result.output and "etag: abc" in result.output and "宝石" in result.output
    assert all(x not in result.output for x in [TOKEN, "not-for-output", "private"])
    (req,) = requests
    assert str(req.url) == "https://api.gitcode.com/api/v8/repos/Acme/tools/actions/runs?branch=a%2Fb"
    assert req.method == "GET" and req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["If-None-Match"] == "old" and "private-token" not in req.headers


def test_generic_get_retains_existing_duplicate_key_handling(call):
    invoke, requests = call
    result = invoke(["user"], [httpx.Response(200, content=b'{"value": 1, "value": 2}')])
    assert result.exit_code == 0 and json.loads(result.output) == {"value": 2}
    assert len(requests) == 1


def test_fields_and_input(call):
    invoke, requests = call
    result = invoke(
        [
            "repos/o/issues",
            "-f",
            "title=123",
            "-F",
            "assignee=42",
            "-F",
            "enabled=true",
            "-F",
            "base=null",
            "-F",
            "name=value",
        ],
        [httpx.Response(201, json={"id": 1})],
    )
    assert result.exit_code == 0
    (req,) = requests
    assert req.method == "POST"
    assert json.loads(req.content) == {"title": "123", "assignee": 42, "enabled": True, "base": None, "name": "value"}
    result = invoke(
        ["repos/o/issues", "--api-version", "v8", "--input", "-", "-f", "filter=abc", "--silent"],
        [httpx.Response(201, json={"id": 2})],
        stdin='{"a":[1,2]}',
    )
    assert result.exit_code == 0 and not result.output
    (req,) = requests
    assert str(req.url) == "https://api.gitcode.com/api/v8/repos/o/issues?filter=abc"
    assert req.headers["content-type"] == "application/json" and json.loads(req.content) == {"a": [1, 2]}


@pytest.mark.parametrize("method,status", [("HEAD", 200), ("DELETE", 204), ("PATCH", 205)])
def test_no_body(call, method, status):
    invoke, requests = call
    result = invoke(["/items/1", "-X", method], [httpx.Response(status)])
    assert result.exit_code == 0 and result.output == ""
    assert requests[0].method == method


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.gitcode.com/api/v5/user",
        "https://example.invalid/a",
        "//example.invalid/",
        "/api/v7/user",
        "/api/v8",
        "api/v5/",
        "api/v5//foo",
        "api/v5/a/../user",
        "user#fragment",
        "repo/%2e%2e/user",
        "r/%252E%252E",
        "user/%2fabc",
        "user/%5Cabc",
        "%61pi/v9/user",
        "graphql",
        "/api/v8/graphql",
        "foo%zz",
        "user/%f0",
        "user/%00",
        "user\n",
        "/user?wat",
        "a?k=%xx",
        "/user?access%5Ftoken=oops",
        "/user?x=a&x=b",
        "/user?k=%0a",
        "/user?Private-Token=x",
    ],
)
def test_invalid_endpoint_never_connects(call, endpoint):
    invoke, requests = call
    result = invoke([endpoint])
    assert result.exit_code != 0 and not requests


@pytest.mark.parametrize(
    "args",
    [
        ["-H", "Authorization: Basic secret"],
        ["-H", "Host: example.invalid"],
        ["-H", "X-HTTP-Method-Override: PUT"],
        ["-H", "Cookie: sid=test"],
        ["-H", "Accept: text/plain\r\nInjected: value"],
        ["-H", "Accept: 宝石"],
        ["-F", "token=override"],
        ["-F", "length"],
        ["-f", "key=a", "-f", "key=b"],
        ["-F", "path=@file"],
        ["--paginate", "-X", "POST"],
        ["--paginate", "-f", "page=2"],
        ["--slurp"],
        ["--slurp", "--paginate", "-i"],
        ["--silent", "--jq", "."],
        ["--input", "-", "-X", "GET"],
        ["-X", "GET", "-f", f"ref={TOKEN}"],
        ["-X", "GET", "-f", "ref=a\nb"],
        ["--api-version", "v8"],
    ],
)
def test_forbidden_options_rejected_preflight(call, args):
    invoke, requests = call
    result = invoke(["/api/v5/user", *args], stdin="{}")
    assert result.exit_code and not requests and TOKEN not in result.output


def test_bad_input_and_scope_never_connect(call, monkeypatch):
    invoke, requests = call
    for args, kw in [
        (["repos/o/r", "--input", "-"], {"stdin": "broken"}),
        (["repos/{owner}/{repo}"], {"repo": "github.com/o/r"}),
        (["repos/o/r"], {"repo": "github.com/o/r"}),
        (["user", "-X", "PATCH"], {"token": ""}),
        (["user"], {"token": "secret\nheader"}),
        (["user?ref=x", "-X", "GET", "-f", "ref=y"], {}),
        (["user?page=-1", "--paginate"], {}),
    ]:
        result = invoke(args, **kw)
        assert result.exit_code and not requests
    monkeypatch.setattr(api, "MAX_BYTES", 2)
    monkeypatch.setattr(rest_api, "MAX_BYTES", 2)
    assert invoke(["user", "--input", "-"], stdin="[12]").exit_code
    assert not requests


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": f"https://foreign.invalid/?token={TOKEN}"}),
        httpx.Response(307, headers={"Location": "https://api.gitcode.com/api/v5/user"}),
        httpx.Response(403, json={"error": "other-private-secret"}),
        httpx.ReadError("other-private-secret"),
        httpx.Response(202),
        httpx.Response(207, json=[]),
        httpx.Response(200, text="other-private-secret"),
        httpx.Response(200, content=b"null"),
        httpx.Response(200, content=b""),
    ],
)
def test_write_outcomes_no_retry_and_no_sensitive_output(call, response):
    invoke, requests = call
    result = invoke(["repos/o/r", "-X", "PUT"], [response])
    assert result.exit_code != 0 and len(requests) == 1
    assert "Verify the remote state" in result.output
    assert all(x not in result.output for x in [TOKEN, "other-private-secret", "foreign.invalid"])


def test_array_paging_fixed_path_and_slurp(call):
    invoke, requests = call
    replies = [
        httpx.Response(
            200,
            json=page,
            headers={"Link": "<https://foreign.invalid/next>; rel=next", "Set-Cookie": "session=example"},
        )
        for page in [[1], [2], []]
    ]
    result = invoke(["repos/o/r/issues?filter=u", "--paginate", "--slurp", "-X", "GET", "-F", "page=2"], replies)
    assert result.exit_code == 0 and json.loads(result.output) == [[1], [2]]
    assert [str(r.url) for r in requests] == [
        f"https://api.gitcode.com/api/v5/repos/o/r/issues?filter=u&page={p}" for p in (2, 3, 4)
    ]
    assert all("cookie" not in r.headers for r in requests)


@pytest.mark.parametrize("pages", [[[1], [2], [1]], [[1], {"unexpected": 2}], [[1], [2], [3]]])
def test_pagination_failures_do_not_emit_partial_pages(call, monkeypatch, pages):
    invoke, _ = call
    monkeypatch.setattr(rest_api, "MAX_PAGES", 3)
    result = invoke(["items", "--paginate"], [httpx.Response(200, json=p) for p in pages])
    assert result.exit_code and "partial result" in result.output and "[" not in result.output


def test_empty_read_sizing_and_anonymous(call, monkeypatch):
    invoke, requests = call
    result = invoke(["items", "--paginate", "--slurp"], [httpx.Response(200, json=[])], token="")
    assert result.exit_code == 0 and json.loads(result.output) == [[]]
    assert "authorization" not in requests[0].headers
    monkeypatch.setattr(rest_api, "MAX_BYTES", 4)
    result = invoke(["items", "--paginate"], [httpx.Response(200, json=[1]), httpx.Response(200, json=[])])
    assert result.exit_code and "limit exceeded" in result.output


def test_jq_failure_after_successful_write_is_not_a_retry(call, monkeypatch):
    invoke, requests = call

    def bad_jq(*args):
        raise ValueError("other-private-secret")

    monkeypatch.setattr(api.shutil, "which", lambda _name: "jq")
    monkeypatch.setattr(api, "_jq", bad_jq)
    result = invoke(["items", "-X", "POST", "-q", "."], [httpx.Response(201, json={"id": 1})])
    assert result.exit_code and "write request succeeded" in result.output and len(requests) == 1
    assert "other-private-secret" not in result.output


def test_jq_success_and_defaults(call, monkeypatch):
    invoke, _ = call
    monkeypatch.setattr(api.shutil, "which", lambda _name: "jq")
    monkeypatch.setattr(api, "_jq", lambda _exe, _query, data: [data["name"], data["count"], data["sequence"]])
    result = invoke(
        ["items", "-q", ".name"], [httpx.Response(200, json={"name": "abc", "count": 2, "sequence": "\u009b123"})]
    )
    assert result.exit_code == 0 and result.output == 'abc\n2\n"\\u009b123"\n'
    with rest_api.open_client() as client:
        assert not client.follow_redirects


def test_delete_refuses_201(call):
    invoke, requests = call
    result = invoke(["repos/o/r", "-X", "DELETE"], [httpx.Response(201, json={"ok": True})])
    assert result.exit_code and "Verify the remote state" in result.output and len(requests) == 1


@pytest.mark.parametrize(
    "args,stdin",
    [
        (["-H", f'If-Match: "{TOKEN}"'], None),
        (["-f", f"description={TOKEN}"], None),
        (["-F", f"name=prefix_{TOKEN}_suffix"], None),
        (["-f", f"{TOKEN}=title"], None),
        (["-f", "_method=DELETE"], None),
        (["-F", "x-http-method-override=DELETE"], None),
        (["--input", "-"], f'{{"normal":[{{"name":"{TOKEN}"}}]}}'),
        (["--input", "-"], f'{{"normal":[{{"{TOKEN}":"x"}}]}}'),
        (["--input", "-"], '{"normal":[{"sEcReT":"other-private-secret"}]}'),
        (["--input", "-"], '{"normal":[{"accesstoken":"other-private-secret"}]}'),
        (["--input", "-"], '{"normal":[{"%61ccess_token":"other-private-secret"}]}'),
        (["--input", "-"], '{"normal":[{"x-http-method-override":"DELETE"}]}'),
        (["--input", "-"], '{"normal":[{"name":"a","name":"b"}]}'),
        (["--input", "-"], json.dumps(TOKEN)),
        (["--input", "-"], json.dumps({"name": TOKEN.replace("synthetic", "%73ynthetic")})),
        (["--input", "-", "-f", f"location={TOKEN}"], '{"valid":true}'),
    ],
)
def test_never_forwards_reserved_keys_or_active_token(call, args, stdin):
    invoke, requests = call
    result = invoke(["items", *args], stdin=stdin)
    assert result.exit_code and not requests
    assert TOKEN not in result.output and "other-private-secret" not in result.output


@pytest.mark.parametrize(
    "args,stdin",
    [(["--input", "-"], '"宝"'), (["-f", "name=very-long-value"], None)],
)
def test_body_size_capped_after_serialization(call, monkeypatch, args, stdin):
    invoke, requests = call
    monkeypatch.setattr(api, "MAX_BYTES", 6)
    monkeypatch.setattr(rest_api, "MAX_BYTES", 6)
    result = invoke(["items", *args], stdin=stdin)
    assert result.exit_code and "size limit" in result.output and not requests


def test_jq_missing_before_write(call, monkeypatch):
    invoke, requests = call
    monkeypatch.setattr(api.shutil, "which", lambda _name: None)
    result = invoke(["items", "-X", "POST", "-q", "."], [])
    assert result.exit_code and "requires the jq executable" in result.output and not requests


@pytest.mark.skipif(shutil.which("jq") is None, reason="external jq unavailable")
@pytest.mark.parametrize(
    "query,expected",
    [
        (".", [[1], [2]]),
        (".[]", [1]),
        ("[.[]]", [[1], [2]]),
        ("[1], [2]", [1]),
        ("env", {}),
    ],
)
def test_real_jq_array_stream_and_empty_environment(call, query, expected):
    invoke, _ = call
    result = invoke(["items", "-q", query], [httpx.Response(200, json=[[1], [2]])])
    assert result.exit_code == 0, result.output
    first, tail = json.JSONDecoder().raw_decode(result.output)
    assert first == expected and TOKEN not in result.output
    if query in {".[]", "[1], [2]"}:
        assert json.loads(result.output[tail:]) == [2]


@pytest.mark.skipif(shutil.which("jq") is None, reason="external jq unavailable")
def test_format_failure_in_later_page_displays_no_partial_stdout(call):
    invoke, _ = call
    result = invoke(
        ["items", "--paginate", "-i", "-q", 'if . == [2] then error("other-private-secret") else . end'],
        [httpx.Response(200, json=data) for data in ([1], [2], [])],
        separate_stderr=True,
    )
    assert result.exit_code and "Unable to format" in result.stderr
    assert result.stdout == ""
    assert "HTTP 200" not in result.stderr and "other-private-secret" not in result.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="external jq unavailable")
def test_jq_oversize_output_is_closed_without_partial_output(call, monkeypatch):
    invoke, _ = call
    monkeypatch.setattr(api, "MAX_BYTES", 128)
    result = invoke(["items", "-q", "range(1000000)"], [httpx.Response(200, json={"a": 1})], separate_stderr=True)
    assert result.exit_code and "output size" in result.stderr and result.stdout == ""


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_not_modified_read_emits_only_safe_headers(call, method):
    invoke, requests = call
    result = invoke(
        ["items", "-i", "-X", method, "-H", 'If-None-Match: "old"'],
        [httpx.Response(304, headers={"ETag": '"old"', "Set-Cookie": "secret-test"})],
    )
    assert result.exit_code == 0 and result.output == 'HTTP 304\netag: "old"\n\n'
    assert len(requests) == 1 and requests[0].headers["if-none-match"] == '"old"'


def test_empty_query_does_not_invoke_strict_parser(monkeypatch):
    def reject_empty(query, **kwargs):
        assert query, "Python 3.10 strict parser rejects an empty query"
        return [("page", "1")]

    monkeypatch.setattr(rest_api, "parse_qsl", reject_empty)
    assert rest_api.endpoint_url("user", None)[1] == {}
    assert rest_api.endpoint_url("user?", None)[1] == {}
    assert rest_api.endpoint_url("user?page=1", None)[1] == {"page": "1"}
