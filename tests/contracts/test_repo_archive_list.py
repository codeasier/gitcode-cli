"""Offline, request-level contracts for read-only archive filters."""

from __future__ import annotations

import inspect
import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command


def row(rid, **fields):
    return {"id": rid, "full_name": f"owner/repo-{rid}", **fields}


@pytest.fixture
def observe(monkeypatch):
    # Click 8.1 mixes stderr by default, 8.2+ captures the two streams separately.
    options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
    cli_runner = CliRunner(**options)

    def run(args, responses):
        calls = []
        replies = iter(responses)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path, dict(request.url.params)))
            status, data = next(replies)
            return httpx.Response(status, json=data)

        transport = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        monkeypatch.setattr(httpx, "Client", lambda **_kw: transport)
        client = GitCodeClient("fixture", base_url="https://offline.invalid/api/v5/")
        monkeypatch.setattr(AppContext, "client", lambda _self: client)
        try:
            result = cli_runner.invoke(main, ["--token", "fixture", "repo", "list", *args])
        finally:
            client.close()
        return result, calls

    return run


def get(path, page, per_page=100):
    return ("GET", f"/api/v5/{path}", {"page": str(page), "per_page": str(per_page), "access_token": "fixture"})


@pytest.mark.parametrize(
    ("args", "path", "first_404"),
    [([], "user/repos", False), (["owner"], "users/owner/repos", False), (["owner"], "orgs/owner/repos", True)],
)
@pytest.mark.parametrize(("flag", "wanted"), [("--archived", True), ("--no-archived", False)])
def test_scopes_and_filter_before_limit(observe, args, path, first_404, flag, wanted):
    # An unrelated (visibility) flag or a status query must not be substituted for archive status.
    misses = [row(i, status=0 if wanted else 2, private=bool(i % 2)) for i in range(100)]
    matches = [row(100, status="关闭" if wanted else "开始"), row(101, archived=wanted), row(102)]
    responses = ([(404, {})] if first_404 else []) + [(200, misses), (200, matches)]
    result, calls = observe([*args, flag, "-L", "2", "--json", "id,isArchived"], responses)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"id": i, "isArchived": wanted} for i in [100, 101]]
    assert calls == ([get("users/owner/repos", 1)] if first_404 else []) + [get(path, 1), get(path, 2)]


@pytest.mark.parametrize(
    ("flag", "status", "archived"),
    [("--archived", "close", True), ("--no-archived", "start", False)],
)
def test_exact_english_gitcode_list_states(observe, flag, status, archived):
    result, calls = observe([flag, "--json", "isArchived"], [(200, [row(1, status=status, archived=archived)])])
    assert result.exit_code == 0 and json.loads(result.stdout) == [{"isArchived": archived}]
    assert calls == [get("user/repos", 1)]


@pytest.mark.parametrize("flag", ["--archived", "--no-archived"])
@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"status": False},
        {"archived": "false"},
        {"status": 2, "archived": False},
        {"status": "close", "archived": False},
        {"status": "start", "archived": True},
        {"status": "start", "archived": 0},
        {"status": "started", "archived": False},
        {"status": "closed", "archived": True},
        {"status": "Close", "archived": True},
        {"status": 1, "private": True},
    ],
)
def test_unknown_or_conflicting_candidate_aborts_without_partial_results(observe, flag, evidence):
    result, calls = observe(
        [flag, "--json", "id"], [(200, [row(10, archived=flag == "--archived"), row(11, **evidence)])]
    )
    assert result.exit_code == 1 and "unknown or conflicting" in result.stderr
    assert result.stdout == ""
    assert calls == [get("user/repos", 1)]


def test_other_filters_compose_and_irrelevant_unknown_cannot_displace_match(observe):
    rows = [
        row(1, private=False, fork=False, language="Go"),  # missing status, but wrong visibility
        row(2, archived=True, private=True, fork=True, language="Go"),
        row(3, archived=True, private=True, fork=False, language="Python"),
        row(4, status="2", private=True, fork=False, language="Go"),
    ]
    result, calls = observe(
        ["--source", "--archived", "--visibility", "private", "-l", "go", "--json", "id"], [(200, rows)]
    )
    assert result.exit_code == 0 and json.loads(result.output) == [{"id": 4}]
    assert calls == [get("user/repos", 1)]


@pytest.mark.parametrize(
    ("options", "evidence"),
    [
        (["--fork"], {}),
        (["--source"], {"fork": "false"}),
        (["--visibility", "public"], {}),
        (["--visibility", "internal"], {"internal": True, "public": True}),
        (["--visibility", "private"], {"private": "false"}),
        (["--language", "Go"], {"language": {}}),
    ],
)
def test_unknown_combined_filters_are_not_false_or_true(observe, options, evidence):
    result, calls = observe(["--archived", *options], [(200, [row(5, status=2, **evidence)])])
    assert result.exit_code == 1 and "combined repository filters" in result.stderr
    assert result.stdout == "" and calls == [get("user/repos", 1)]


def test_unfiltered_json_keeps_unknown_rows(observe):
    rows = [row(1), row(2, status=2), row(3, status="start"), row(4, status="close"), row(5, status="closed")]
    result, calls = observe(["--json", "id,isArchived"], [(200, rows)])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [
        {"id": i, "isArchived": v} for i, v in enumerate([None, True, False, True, None], 1)
    ]
    assert calls[0][2]["per_page"] == "30" and len(calls) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["--archived", "--no-archived"],
        ["--no-archived", "--archived"],
        ["--archived", "--limit", "0"],
        ["--archived", ".."],
        ["--archived", "fake?owner"],
        ["--no-archived", "owner%2Frepos"],
    ],
)
def test_invalid_invocations_make_no_requests(observe, args):
    result, calls = observe(args, [])
    assert result.exit_code == 2 and not calls


@pytest.mark.parametrize("flag", ["--archived", "--no-archived"])
def test_proxy_remains_closed(flag):
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["repo", "list", "owner", flag])


@pytest.mark.parametrize("bad", [{"items": []}, [None], [{}], [row(i, status=2) for i in range(101)]])
def test_filtered_scan_rejects_invalid_pages(observe, bad):
    result, calls = observe(["--archived", "--json", "id"], [(200, bad)])
    assert result.exit_code == 1 and result.stdout == ""
    assert calls == [get("user/repos", 1)]


def test_page_ceiling_without_silent_empty_result(observe):
    responses = [(200, [row(i + 100 * page, status=0) for i in range(100)]) for page in range(100)]
    result, calls = observe(["--archived"], responses)
    assert result.exit_code == 1 and "incomplete" in result.stderr
    assert calls == [get("user/repos", page) for page in range(1, 101)]


@pytest.mark.parametrize("code", [401, 403, 404])
def test_later_errors_cannot_switch_scope(observe, code):
    result, calls = observe(["owner", "--archived"], [(200, [row(i, status=0) for i in range(100)]), (code, {})])
    assert result.exit_code == 1 and result.stdout == ""
    assert calls == [get("users/owner/repos", 1), get("users/owner/repos", 2)]


@pytest.mark.parametrize("tail", [row(1, status=0), row("001", status=0), {"status": 0}, None])
def test_match_limit_cannot_hide_malformed_tail_in_fetched_page(observe, tail):
    result, calls = observe(["--archived", "-L", "1", "--json", "id"], [(200, [row(1, status=2), tail])])
    assert result.exit_code == 1 and "repository list response" in result.stderr
    assert result.stdout == ""
    assert calls == [get("user/repos", 1)]


def test_match_limit_cannot_hide_overlapping_identity_in_fetched_page(observe):
    misses = [row(i, status=0) for i in range(1, 101)]
    result, calls = observe(
        ["--archived", "-L", "1", "--json", "id"],
        [(200, misses), (200, [row(101, status=2), row(9, status=2)])],
    )
    assert result.exit_code == 1 and "repeated" in result.stderr
    assert result.stdout == ""
    assert calls == [get("user/repos", 1), get("user/repos", 2)]


def test_stop_after_first_fetched_page_when_limit_is_met(observe):
    full = [row(1, status=2), *[row(i) for i in range(2, 101)]]
    result, calls = observe(["--archived", "-L", "1", "--json", "id"], [(200, full)])
    assert result.exit_code == 0 and json.loads(result.stdout) == [{"id": 1}]
    assert calls == [get("user/repos", 1)]


def test_plain_list_retains_user_then_org_fallback_on_each_page(observe):
    result, calls = observe(
        ["owner", "-L", "2", "--fork", "--json", "nameWithOwner"],
        [
            (404, {}),
            (200, [{"full_name": "owner/source"}, {"full_name": "owner/fork", "fork": True}]),
            (404, {}),
            (200, [{"full_name": "owner/fork2", "fork": True}]),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"nameWithOwner": "owner/fork"}, {"nameWithOwner": "owner/fork2"}]
    assert calls == [get(f"{scope}/owner/repos", page, 2) for page in (1, 2) for scope in ("users", "orgs")]
