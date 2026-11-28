"""Workflow registration is current and anonymous; the file is an immutable, read-only repository snapshot."""

from __future__ import annotations

import base64
import hashlib
import json
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.compat.registry import iter_entries, render_markdown_report
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command
from gitcode_cli.repo_read import MAX_RESPONSE
from gitcode_cli.repo_read_file import MAX_FILE

COMMIT = "abcde" * 8
TOKEN = "fixture-T/O+ken"
WF = ".gitcode/workflows/build.yaml"
V5 = "/api/v5/repos/o/r/"
V8 = "/api/v8/repos/o/r/actions/workflows"
ROW = {"workflow_id": "id", "file_path": WF, "name": "构建", "state": "active"}
RAW = "name: 编译\r\njobs:\n  x: !unknown-tag &a '*'".encode()


def oid(kind, raw):
    return hashlib.sha1(f"{kind} {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


def entry(name, mode, sha):
    return {
        "name": name,
        "path": name,
        "sha": sha,
        "type": {"040000": "tree", "160000": "commit"}.get(mode, "blob"),
        "mode": mode,
    }


def one_tree_oid(row):
    return oid(
        "tree", row["mode"].lstrip("0").encode() + b" " + row["name"].encode() + b"\0" + bytes.fromhex(row["sha"])
    )


def sequence(raw=RAW, *, mode="100644", parent_mode="040000", root_mode="040000", filename="build.yaml"):
    path = ".gitcode/workflows/" + filename
    leaf = entry(filename, mode, oid("blob", raw))
    parent = entry("workflows", parent_mode, one_tree_oid(leaf))
    root = entry(".gitcode", root_mode, one_tree_oid(parent))
    page = {"page": "1", "per_page": "100"}
    return [
        (V8, page, {"total_count": 1, "workflows": [{**ROW, "file_path": path}]}),
        (V5 + "commits/" + COMMIT, {}, {"sha": COMMIT}),
        (V5 + "git/trees/" + COMMIT, page, {"tree": [root]}),
        (V5 + "git/trees/" + root["sha"], page, {"tree": [parent]}),
        (V5 + "git/trees/" + parent["sha"], page, {"tree": [leaf]}),
        (
            V5 + "contents/" + path,
            {"ref": COMMIT},
            {
                "name": filename,
                "path": path,
                "type": "file",
                "encoding": "base64",
                "size": len(raw),
                "sha": leaf["sha"],
                "content": base64.b64encode(raw).decode(),
                "download_url": "https://must-not-be-followed.invalid/secret-file",
            },
        ),
    ]


@pytest.fixture
def wire(monkeypatch, tmp_config_dir):
    calls = []
    replies = []

    def respond(transport, request):
        calls.append(request)
        path, params, result = replies.pop(0)
        assert request.method == "GET" and not request.content
        assert request.url.scheme == "https" and request.url.host == "api.gitcode.com" and request.url.path == path
        assert dict(request.url.params) == params
        assert all(key not in request.headers for key in ("cookie", "private-token"))
        assert request.headers.get("accept-encoding") == "identity"
        if path == V8:
            assert "authorization" not in request.headers
        else:
            assert request.headers.get("authorization") == "Bearer " + TOKEN
        if "access_token" not in params:
            assert TOKEN not in str(request.url) and "access_token" not in str(request.url)
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result, headers={"Set-Cookie": "never=forwarded"})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", respond)
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))

    def invoke(*args, global_args=(), token=TOKEN):
        return runner.invoke(main, ["--token", token, *global_args, "workflow", "view", *args])

    yield replies.extend, invoke, calls
    assert not replies


ARGS = ["id", "--yaml", "--ref", COMMIT, "-R", "o/r"]


def failed(result):
    assert result.exit_code != 0, result.output
    assert result.stdout_bytes == b"" and result.stderr and not isinstance(result.exception, AssertionError)
    assert TOKEN not in result.stderr


@pytest.mark.parametrize(
    ("selector", "filename", "mode", "raw"),
    [("id", "build.yml", "100755", b""), ("构建", "build.yaml", "100644", RAW), (WF, "build.yaml", "100644", b"\t#\n")],
)
def test_exact_text_and_request_binding(wire, selector, filename, mode, raw):
    expect, invoke, calls = wire
    expect(sequence(raw, mode=mode, filename=filename))
    result = invoke(selector, "--yaml", "--ref", COMMIT.upper(), global_args=("-R", "o/r"))
    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == raw and result.stderr == "" and len(calls) == 6


@pytest.mark.parametrize(
    "args",
    [
        ["id", "--yaml", "-R", "o/r"],
        ["id", "--ref", COMMIT, "-R", "o/r"],
        ["id", "--yaml", "--ref", COMMIT],
        ["id", "--yaml", "--ref", "main", "-R", "o/r"],
        ["id", "--yaml", "--ref", "0" * 40, "-R", "o/r"],
        ["id", "--yaml", "--ref", "a" * 64, "-R", "o/r"],
        [*ARGS, "--ref", COMMIT],
        [*ARGS[:-1], "gitcode.com/o/r"],
        [*ARGS[:-1], "../r"],
        [*ARGS[:-1], "o/r%2Fjunk"],
    ],
)
def test_reject_bad_flags_before_transport(wire, args):
    _, invoke, calls = wire
    failed(invoke(*args))
    assert not calls


def test_target_conflict_and_token_in_anonymous_repo(wire):
    _, invoke, calls = wire
    failed(invoke(*ARGS, global_args=("-R", "other/r")))
    failed(invoke(*ARGS[:-1], "o/fixture", token="fixture"))
    assert not calls


def test_legacy_view_uses_unchanged_native_endpoint_and_metadata(wire):
    expect, invoke, calls = wire
    other = {**ROW, "workflow_id": "different"}
    expect(
        [(V8, {"access_token": TOKEN, "page": "1", "per_page": "100"}, {"total_count": 2, "workflows": [ROW, other]})]
    )
    result = invoke("id", "-R", "o/r")
    assert result.exit_code == 0 and result.stdout == json.dumps(ROW, indent=2, ensure_ascii=True) + "\n"
    assert result.stderr == "" and len(calls) == 1


@pytest.mark.parametrize(
    "path",
    [
        "workflows/a.yml",
        ".gitcode/workflows/.x.yml",
        ".gitcode/workflows/n/a.yml",
        ".atomgit/workflows/a.yml",
        ".gitcode/workflows/%2e/a.yml",
        ".gitcode/workflows/a.YML",
        ".gitcode/workflows/a.yml?token",
        "https://other/a.yml",
        ".gitcode/workflows/a\x1b.yml",
        ".gitcode/workflows/a",
    ],
)
def test_untrusted_registration_path_stops_before_v5(wire, path):
    expect, invoke, calls = wire
    expect([(V8, {"page": "1", "per_page": "100"}, {"total_count": 1, "workflows": [{**ROW, "file_path": path}]})])
    failed(invoke(*ARGS))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "rows",
    [
        [ROW, {**ROW, "workflow_id": "different"}],
        [ROW, ROW],
        [ROW, {**ROW, "workflow_id": "other", "name": "id", "file_path": ".gitcode/workflows/other.yml"}],
        [{**ROW, "workflow_id": ""}],
        [{**ROW, "file_path": None}],
        [],
    ],
)
def test_ambiguous_registration_never_loads_files(wire, rows):
    expect, invoke, calls = wire
    expect([(V8, {"page": "1", "per_page": "100"}, {"total_count": len(rows), "workflows": rows})])
    failed(invoke(*ARGS))
    assert len(calls) == 1


def test_registration_ambiguity_on_later_page(wire):
    expect, invoke, calls = wire
    rows = [ROW] + [{**ROW, "workflow_id": f"id-{i}", "file_path": f".gitcode/workflows/{i}.yml"} for i in range(99)]
    expect(
        [
            (V8, {"page": "1", "per_page": "100"}, {"total_count": 101, "workflows": rows}),
            (V8, {"page": "2", "per_page": "100"}, {"total_count": 101, "workflows": [{**ROW, "workflow_id": "late"}]}),
        ]
    )
    failed(invoke(*ARGS, "--scan-limit", "101"))
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("kw", "n"),
    [({"root_mode": "120000"}, 3), ({"parent_mode": "160000"}, 4), ({"mode": "120000"}, 5), ({"mode": "160000"}, 5)],
)
def test_all_tree_modes_are_checked(wire, kw, n):
    expect, invoke, calls = wire
    expect(sequence(**kw)[:n])
    failed(invoke(*ARGS))
    assert len(calls) == n


@pytest.mark.parametrize(
    ("i", "replace"),
    [
        (1, {"sha": "e" * 40}),
        (1, []),
        (2, {"tree": [], "truncated": True}),
        (2, {"tree": []}),
        (3, {"tree": [entry("workflows", "040000", COMMIT)]}),
        (4, {"tree": [entry("build.yaml", "100755", COMMIT)]}),
        (5, {**sequence()[-1][2], "path": "other"}),
        (5, {**sequence()[-1][2], "sha": "c" * 40}),
        (5, sequence(b"other self-consistent bytes")[-1][2]),
        (5, {**sequence()[-1][2], "size": MAX_FILE + 1}),
        (5, {**sequence()[-1][2], "content": "??"}),
        (5, {**sequence()[-1][2], "type": "symlink"}),
    ],
)
def test_wrong_identity_or_incomplete_data_no_partial_output(wire, i, replace):
    expect, invoke, calls = wire
    seq = sequence()[: i + 1]
    seq[i] = (*seq[i][:2], replace)
    expect(seq)
    failed(invoke(*ARGS))
    assert len(calls) == i + 1


@pytest.mark.parametrize("i", range(6))
def test_never_follow_redirects_retry_auth_or_read_raw(wire, i):
    expect, invoke, calls = wire
    seq = sequence()[: i + 1]
    seq[i] = (*seq[i][:2], httpx.Response(302, headers={"Location": "https://other.invalid/test"}))
    expect(seq)
    failed(invoke(*ARGS))
    assert len(calls) == i + 1


@pytest.mark.parametrize(
    "data",
    [
        TOKEN.encode(),
        b"fixture-T%2fO%2bken",
        b"fi%78ture-T%2FO%2Bken",
        b"fixture-T%252fO%252bken",
        b"safe prefix\nunsafe \x1b[31m",
        "rule\u202e".encode(),
        b"raw\xff",
        b"standalone\rCR",
    ],
)
def test_unsafe_final_blob_is_not_written(wire, data):
    expect, invoke, calls = wire
    expect(sequence(b"name: " + data))
    failed(invoke(*ARGS))
    assert len(calls) == 6


def test_known_oversize_response_never_exposes_prefix(wire):
    expect, invoke, calls = wire
    seq = sequence()
    seq[-1] = (*seq[-1][:2], httpx.Response(200, content=b" " * (MAX_RESPONSE + 1)))
    expect(seq)
    failed(invoke(*ARGS))
    assert len(calls) == 6


def test_no_authenticated_catalog_fallback(wire):
    expect, invoke, calls = wire
    expect([(V8, {"page": "1", "per_page": "100"}, httpx.Response(401, text="unused"))])
    failed(invoke(*ARGS))
    assert len(calls) == 1


def test_exact_file_limit_and_final_newline_preserved(wire):
    expect, invoke, _ = wire
    body = b"#" * (MAX_FILE - 1) + b"\n"
    expect(sequence(body))
    result = invoke(*ARGS)
    assert result.exit_code == 0 and result.stdout_bytes == body


def test_root_entry_on_second_page(wire):
    expect, invoke, _ = wire
    seq = sequence()
    first = [entry(f"x{i}", "100644", "d" * 40) for i in range(100)]
    second = (seq[2][0], {"page": "2", "per_page": "100"}, seq[2][2])
    seq[2:3] = [(seq[2][0], seq[2][1], {"tree": first}), second]
    expect(seq)
    result = invoke(*ARGS)
    assert result.exit_code == 0 and result.stdout_bytes == RAW


def test_duplicate_root_across_pages_fails_even_if_path_seen(wire):
    expect, invoke, calls = wire
    seq = sequence()[:3]
    page = seq[2][2]["tree"]
    page.extend(entry(f"x{i}", "100644", "d" * 40) for i in range(99))
    expect([*seq, (seq[2][0], {"page": "2", "per_page": "100"}, {"tree": [page[0]]})])
    failed(invoke(*ARGS))
    assert len(calls) == 4


def test_root_with_no_terminal_page_within_scan_bound(wire):
    expect, invoke, calls = wire
    seq = sequence()
    chunks = [
        (
            seq[2][0],
            {"page": str(i), "per_page": "100"},
            {"tree": [entry(f"x{i}_{j}", "100644", "d" * 40) for j in range(100)]},
        )
        for i in range(1, 11)
    ]
    expect([*seq[:2], *chunks])
    failed(invoke(*ARGS))
    assert len(calls) == 12


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, content=b'{"sha":"a","sha":"b"}', headers={"content-type": "application/json"}),
        httpx.Response(200, json={"sha": COMMIT}, headers={"content-type": "text/html"}),
        httpx.Response(200, json={"sha": COMMIT}, headers={"content-encoding": "identity, identity"}),
    ],
)
def test_untrusted_commit_envelope(wire, reply):
    expect, invoke, _ = wire
    seq = sequence()[:2]
    seq[1] = (*seq[1][:2], reply)
    expect(seq)
    failed(invoke(*ARGS))


def test_compat_report_and_proxy_preserve_direct_only_boundary():
    rows = {entry.flag: entry for entry in iter_entries(groups=["workflow"]) if entry.command == "workflow view"}
    assert set(rows) == {None, "--yaml", "--ref"}
    assert "Default: workflow metadata" in rows[None].note
    report = render_markdown_report()
    for flag in ("--yaml", "--ref"):
        row = rows[flag]
        assert row.status.value == "implemented"  # documented approximation, not GitHub equivalence
        assert not row.gc_extension and not row.proxy_allowed
        assert f"| `workflow view` | `{flag}` | implemented | Partial, direct gc only:" in report
    with pytest.raises(ProxyError, match="use gc workflow view directly"):
        validate_gitcode_command(["workflow", "view", *ARGS])


def test_yaml_help_describes_limits_without_changing_legacy_defaults(wire):
    _, invoke, calls = wire
    result = invoke("--help")
    assert result.exit_code == 0
    assert all(s in result.stdout for s in ("--yaml", "--ref COMMIT", "currently registered public", "nonzero SHA-1"))
    assert not calls
