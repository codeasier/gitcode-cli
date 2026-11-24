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
        root = ["-R", repo] if repo is not None else []
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


RUNS_PATH = "/api/v8/repos/o/r/actions/runs"


def _runs_envelope(total, *ids, **other):
    return {"total_count": total, "workflow_runs": [{"workflow_run_id": run_id} for run_id in ids], **other}


def test_v8_runs_page_objects_are_redacted_and_requests_remain_pinned(call):
    invoke, requests = call
    first = _runs_envelope(3, "run-1", "run-2", record={"token": "do-not-print", "message": TOKEN})
    second = _runs_envelope(3, "run-3", extra={"retain": "upstream JSON"})
    result = invoke(
        [
            "/api/v8/repos/{owner}/{repo}/actions/runs?branch=release%2Fv1&per_page=2",
            "-X",
            "GET",
            "-f",
            "event=Push",
            "--paginate",
            "--slurp",
        ],
        [
            httpx.Response(
                200,
                headers={
                    "X-Page": str(page),
                    "X-Per-Page": "2",
                    "X-Next-Page": "2" if page == 1 else "",
                    "X-Prev-Page": "1" if page == 2 else "",
                    "X-Total": "3",
                    "X-Total-Pages": "2",
                    "Set-Cookie": "sid=private",
                },
                json=data,
            )
            for page, data in enumerate((first, second), 1)
        ],
        repo="gitcode.com/o/r",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{**first, "record": {"token": "[REDACTED]", "message": "[REDACTED]"}}, second]
    assert all(x not in result.output for x in ("foreign.invalid", "do-not-print", TOKEN))
    assert [r.url.params["page"] for r in requests] == ["1", "2"]
    for r in requests:
        assert r.method == "GET" and r.url.host == "api.gitcode.com" and r.url.path == RUNS_PATH and not r.content
        assert dict(r.url.params) == {
            "branch": "release/v1",
            "per_page": "2",
            "page": r.url.params["page"],
            "event": "Push",
        }
        assert r.headers["authorization"] == f"Bearer {TOKEN}"
        assert r.headers["Accept-Encoding"] == "identity"
        assert not {"cookie", "private-token"}.intersection(r.headers)


@pytest.mark.parametrize(
    "args",
    [[RUNS_PATH, "--paginate"], [RUNS_PATH.removeprefix("/api/v8/"), "--api-version", "v8", "--paginate", "-i"]],
)
def test_v8_runs_empty_envelope_and_explicit_default_page_size(call, args):
    invoke, requests = call
    empty = _runs_envelope(0)
    result = invoke(args, [httpx.Response(200, json=empty)], token="")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output.split("\n\n", 1)[-1]) == empty
    (req,) = requests
    assert req.url.path == RUNS_PATH and dict(req.url.params) == {"page": "1", "per_page": "20"}
    assert "authorization" not in req.headers


def test_v8_runs_non_slurped_pages_are_raw_root_objects(call):
    invoke, requests = call
    pages = [_runs_envelope(2, "A", custom="first"), _runs_envelope(2, "B", custom="second")]
    result = invoke(
        [f"{RUNS_PATH}?page=1&per_page=1", "--paginate"], [httpx.Response(200, json=page) for page in pages]
    )
    assert result.exit_code == 0, result.output
    first, end = json.JSONDecoder().raw_decode(result.output)
    assert first == pages[0] and json.loads(result.output[end:]) == pages[1]
    assert [r.url.params["page"] for r in requests] == ["1", "2"]


@pytest.mark.parametrize(
    ("path", "other", "repo"),
    [
        (RUNS_PATH, [], "o/other"),
        (RUNS_PATH, [], ""),
        (RUNS_PATH, [], "gitcode.com:8443/o/r"),
        (RUNS_PATH, [], "ssh.gitcode.com/o/r"),
        (RUNS_PATH.replace("/o/r/", "/o/{repo}/"), [], "other/r"),
        (RUNS_PATH.replace("/o/r/", "/{owner}/r/"), [], "o/other"),
        (RUNS_PATH.replace("/o/r/", "/%E5%AE%9D/r/"), [], None),
        (RUNS_PATH + "?page=2", [], None),
        (RUNS_PATH + "?page=01", [], None),
        (RUNS_PATH + "?per_page=0", [], None),
        (RUNS_PATH + "?per_page=101", [], None),
        (RUNS_PATH + "?per_page=1.0", [], None),
        (RUNS_PATH + "?per_page=010", [], None),
        (RUNS_PATH + "?page=1&Page=2", [], None),
        (RUNS_PATH + "?per_page=2", ["-X", "GET", "-F", "per_page=3"], None),
        (RUNS_PATH + "?start_time=1", [], None),
        (RUNS_PATH + "?branch=", [], None),
        (RUNS_PATH + "?branch=" + "a" * 1025, [], None),
        (RUNS_PATH, ["-H", "If-None-Match: example"], None),
        (RUNS_PATH, ["-H", "Accept: text/plain"], None),
        (RUNS_PATH, ["-X", "HEAD"], None),
        (RUNS_PATH, ["-X", "PUT"], None),
    ],
)
def test_v8_runs_refuses_unclear_scope_or_options_before_connecting(call, path, other, repo):
    invoke, requests = call
    result = invoke([path, "--paginate", *other], repo=repo, separate_stderr=True)
    assert result.exit_code != 0 and requests == [] and not result.stdout
    assert ("error:" in result.stderr.lower() or "usage:" in result.stderr.lower()) and TOKEN not in result.stderr


@pytest.mark.parametrize(
    "other",
    [
        _runs_envelope(4, "C", "D"),
        _runs_envelope(3),
        _runs_envelope(3, "C", "D"),
        _runs_envelope(3, "A", details="distinct data cannot bypass duplicate ID detection"),
        _runs_envelope(3, ""),
        _runs_envelope(3, 42),
        _runs_envelope(3, " padded"),
        _runs_envelope(3, "C\u0000"),
        {"total_count": 3, "workflow_runs": [None]},
        {"total_count": 3, "workflow_runs": [{"id": "C"}]},
        {"total_count": True, "workflow_runs": []},
        {"total_count": "3", "workflow_runs": []},
        {"total_count": -1, "workflow_runs": []},
        {"total_count": 3, "runs": [{"workflow_run_id": "C"}]},
        _runs_envelope(3, "C", next_page=3),
        _runs_envelope(3, "C", page=1),
        _runs_envelope(3, "C", per_page=1),
        [{"workflow_run_id": "C"}],
    ],
)
def test_v8_runs_incomplete_or_overlapping_pages_never_emit_partial_data(call, other):
    invoke, requests = call
    result = invoke(
        [f"{RUNS_PATH}?per_page=2", "--paginate", "-i"],
        [
            httpx.Response(200, json=_runs_envelope(3, "A", "B", exposed="no-sample-text")),
            httpx.Response(200, json=other),
        ],
        separate_stderr=True,
    )
    assert result.exit_code != 0 and len(requests) == 2 and result.stdout == ""
    assert "no-sample-text" not in result.stderr and "HTTP 200" not in result.stderr


@pytest.mark.parametrize(
    "raw",
    [
        b'{"total_count": 1, "total_count": 0, "workflow_runs": []}',
        b'{"total_count": 1, "workflow_runs": [{"workflow_run_id":"x", "workflow_run_id":"y"}]}',
        b'{"total_count": 0, "workflow_runs": [], "extra": NaN}',
        b'{"total_count": 0, "workflow_runs": [], "extra": 1e999}',
    ],
)
def test_v8_runs_refuses_duplicate_keys_and_nonfinite_numbers(call, raw):
    invoke, _ = call
    result = invoke([RUNS_PATH, "--paginate", "--silent"], [httpx.Response(200, content=raw)], separate_stderr=True)
    assert result.exit_code != 0 and not result.stdout


class _UnreadStream(httpx.SyncByteStream):
    def __iter__(self):
        pytest.fail("The refused body must not be consumed")
        yield b""


@pytest.mark.parametrize(
    "status,headers",
    [
        (200, {"Content-Encoding": "gzip"}),
        (200, {"Content-Range": "items 0-0/2"}),
        (200, {"Link": '<https://foreign.invalid/api/v8/repos/o/r/actions/runs?page=2>; rel="next"'}),
        (200, {"Link": '<https://api.gitcode.com/api/v8/repos/o/r/actions/runs?page=2>; rel="next"'}),
        (200, {"X-Page": "9"}),
        (200, {"X-Per-Page": "999"}),
        (206, {}),
        (204, {}),
        (304, {}),
        (302, {"Location": "https://foreign.invalid"}),
    ],
)
def test_v8_runs_requires_uncompressed_http_200_and_does_not_follow_links(call, status, headers):
    invoke, requests = call
    result = invoke(
        [RUNS_PATH, "--paginate"],
        [httpx.Response(status, headers=headers, stream=_UnreadStream())],
        separate_stderr=True,
    )
    assert result.exit_code != 0 and len(requests) == 1 and not result.stdout
    assert "foreign.invalid" not in result.stderr


def test_v8_runs_total_limit_stops_on_first_response(call, monkeypatch):
    invoke, requests = call
    monkeypatch.setattr(rest_api, "MAX_PAGES", 2)
    result = invoke(
        [RUNS_PATH + "?per_page=1", "--paginate"],
        [httpx.Response(200, json=_runs_envelope(3, "A"))],
        separate_stderr=True,
    )
    assert result.exit_code != 0 and len(requests) == 1 and not result.stdout
    assert "pagination limit" in result.stderr


def test_v8_runs_byte_cap_is_aggregate_and_fails_before_any_output(call, monkeypatch):
    invoke, requests = call
    first = httpx.Response(200, json=_runs_envelope(2, "A", additional="A" * 100))
    second = httpx.Response(200, json=_runs_envelope(2, "B", additional="B" * 100))
    monkeypatch.setattr(rest_api, "MAX_BYTES", len(first.content) + len(second.content) - 1)
    result = invoke([RUNS_PATH + "?per_page=1", "--paginate"], [first, second], separate_stderr=True)
    assert result.exit_code != 0 and len(requests) == 2 and not result.stdout
    assert "size limit" in result.stderr


@pytest.mark.parametrize(
    "path", [RUNS_PATH.replace("/v8/", "/v5/"), RUNS_PATH + "/1", RUNS_PATH.replace("/runs", "/artifacts")]
)
def test_v8_runs_policy_does_not_extend_to_other_envelopes(call, path):
    invoke, requests = call
    result = invoke([path, "--paginate"], [httpx.Response(200, json=_runs_envelope(0))], separate_stderr=True)
    assert result.exit_code != 0 and len(requests) == 1 and not result.stdout
    assert "requires a JSON array" in result.stderr


@pytest.mark.parametrize("path", [RUNS_PATH, RUNS_PATH.replace("/o/r/", "/{owner}/{repo}/")])
def test_v8_runs_never_infers_origin_for_explicit_routes_or_placeholders(call, monkeypatch, path):
    invoke, requests = call

    def refuse_origin(_repo):
        pytest.fail("v8 run pagination must not resolve a local origin")

    monkeypatch.setattr(api, "resolve_repo", refuse_origin)
    if "{owner}" in path:
        result = invoke([path, "--paginate"], separate_stderr=True)
        assert result.exit_code != 0 and not result.stdout and not requests
        assert "explicit -R" in result.stderr and TOKEN not in result.stderr
    else:
        result = invoke([path, "--paginate"], [httpx.Response(200, json=_runs_envelope(0))])
        assert result.exit_code == 0 and len(requests) == 1


@pytest.mark.parametrize(
    ("token", "path", "sent"),
    [
        ("20", RUNS_PATH, 0),
        ("2", RUNS_PATH + "?per_page=1", 1),
        ("page=2", RUNS_PATH + "?per_page=1", 1),
    ],
)
def test_v8_runs_rechecks_token_after_generating_pagination_params(call, token, path, sent):
    invoke, requests = call
    result = invoke(
        [path, "--paginate", "-i"],
        [httpx.Response(200, json=_runs_envelope(2, "A", tag="never-printed"))][:sent],
        token=token,
        separate_stderr=True,
    )
    assert result.exit_code != 0 and not result.stdout and len(requests) == sent
    assert "outside the authorization header" in result.stderr
    assert "never-printed" not in result.stderr and token not in result.stderr
    assert all(token not in str(request.url) for request in requests)


@pytest.mark.parametrize(
    ("total", "run_page", "headers"),
    [
        (0, _runs_envelope(0), {"X-Next-Page": "2"}),
        (0, _runs_envelope(0), {"X-Total": "2"}),
        (0, _runs_envelope(0), {"X-Total-Pages": "2"}),
        (0, _runs_envelope(0), {"X-Prev-Page": "1"}),
        (2, _runs_envelope(2, "A"), {"X-Next-Page": ""}),
        (2, _runs_envelope(2, "A"), {"X-Next-Page": "3"}),
        (2, _runs_envelope(2, "A"), {"X-Next-Page": "2, 2"}),
    ],
)
def test_v8_runs_rejects_continuation_headers_conflicting_with_the_body(call, total, run_page, headers):
    invoke, requests = call
    assert run_page["total_count"] == total
    result = invoke(
        [RUNS_PATH + "?per_page=1", "--paginate", "-i"],
        [httpx.Response(200, json=run_page, headers=headers)],
        separate_stderr=True,
    )
    assert result.exit_code != 0 and len(requests) == 1 and result.stdout == ""
    assert "Contradictory" in result.stderr and "HTTP 200" not in result.stderr and TOKEN not in result.stderr


def test_v8_runs_cannot_substitute_the_fixed_actions_runs_suffix(call):
    invoke, requests = call
    result = invoke(["/api/v8/repos/o/r/{owner}/{repo}", "--paginate"], repo="actions/runs", separate_stderr=True)
    assert result.exit_code != 0 and not result.stdout and not requests
    assert "literal actions/runs" in result.stderr and TOKEN not in result.stderr


@pytest.mark.parametrize("later_page", [False, True])
@pytest.mark.parametrize(
    ("header", "body"),
    [
        ([("X-Truncated", "true")], {}),
        ([("X-Truncated", "1")], {}),
        ([("X-Incomplete-Results", "True")], {}),
        ([("X-Incomplete-Results", "unknown")], {}),
        ([("X-Truncated", "")], {}),
        ([("X-Truncated", "false"), ("x-truncated", "true")], {}),
        ([("X-INCOMPLETE-RESULTS", "0"), ("X-Incomplete-Results", "1")], {}),
        ([], {"truncated": True}),
        ([], {"truncated": 1}),
        ([], {"truncated": None}),
        ([], {"truncated": 0.0}),
        ([], {"incomplete_results": True}),
        ([], {"incomplete_results": "false"}),
        ([("X-Truncated", "false")], {"truncated": True}),
        ([("X-Incomplete-Results", "1")], {"incomplete_results": False}),
    ],
)
def test_v8_runs_rejects_partial_indicators_without_emitting_pages(call, later_page, header, body):
    invoke, requests = call
    responses = [httpx.Response(200, json=_runs_envelope(2, "A", marker="first-page-private"))] if later_page else []
    final = _runs_envelope(2, "B", **body) if later_page else _runs_envelope(0, **body)
    responses.append(httpx.Response(200, json=final, headers=header))
    result = invoke([RUNS_PATH + "?per_page=1", "--paginate", "-i"], responses, separate_stderr=True)
    assert result.exit_code != 0 and not result.stdout and len(requests) == len(responses)
    assert "truncation" in result.stderr
    assert all(value not in result.stderr for value in (TOKEN, "first-page-private", "HTTP 200"))


def test_v8_runs_accepts_unambiguous_false_indicators(call):
    invoke, requests = call
    envelope = _runs_envelope(0, truncated=False, incomplete_results=0)
    result = invoke(
        [RUNS_PATH, "--paginate", "--slurp"],
        [httpx.Response(200, json=envelope, headers={"X-Truncated": "False", "X-Incomplete-Results": "0"})],
    )
    assert result.exit_code == 0 and len(requests) == 1
    assert json.loads(result.output) == [envelope]


def test_v8_runs_rejects_duplicate_body_indicators_even_with_final_false(call):
    invoke, requests = call
    result = invoke(
        [RUNS_PATH, "--paginate", "--slurp"],
        [httpx.Response(200, content=b'{"total_count":0,"workflow_runs":[],"truncated":true,"truncated":false}')],
        separate_stderr=True,
    )
    assert result.exit_code != 0 and len(requests) == 1 and not result.stdout
    assert "valid JSON" in result.stderr and TOKEN not in result.stderr
