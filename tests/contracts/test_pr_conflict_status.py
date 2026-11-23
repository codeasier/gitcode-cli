"""Offline, read-only command contract for the GitCode repository conflict view."""

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

TOKEN = "status-contract-synthetic"
BASE = "https://conflict.invalid/api/v5/"
PREFIX = "/api/v5/repos/o/r/pulls"
PAGE = {"state": "open", "page": "1", "per_page": "20"}
ROW = {"number": 7, "id": 107, "state": "open", "title": "First"}


@pytest.fixture
def invoke(monkeypatch):
    def run(args, *expected):
        steps = iter(expected)

        def respond(request):
            step = next(steps, None)
            assert step is not None, "Unexpected additional request"
            suffix, query, status, payload = step
            assert request.method == "GET" and request.url.host == "conflict.invalid"
            assert request.url.path == PREFIX + suffix and not request.content
            assert sorted(request.url.params.multi_items()) == sorted({"access_token": TOKEN, **query}.items())
            return httpx.Response(status, json=payload)

        with httpx.Client(transport=httpx.MockTransport(respond)) as mocked:
            monkeypatch.setattr("gitcode_cli.client.httpx.Client", lambda **_: mocked)
            monkeypatch.setattr(AppContext, "client", lambda _: GitCodeClient(TOKEN, base_url=BASE))
            result = CliRunner().invoke(main, ["--token", TOKEN, "-R", "o/r", "pr", "status", *args])
        assert next(steps, None) is None
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        return result

    return run


def test_without_conflict_flag_preserves_single_list_and_output(invoke):
    result = invoke([], ("", {"state": "open"}, 200, [ROW]))
    assert result.exit_code == 0
    assert result.output.endswith("  #7\topen\tFirst\n") and "conflict" not in result.output.lower()


@pytest.mark.parametrize(
    "gates,expected",
    [
        ({"conflict_passed": True, "merge_request_id": 107}, "passed"),
        ({"conflict_passed": False}, "not passed"),
        ({"conflict_passed": None}, "unknown"),
        ({"conflict_passed": 0}, "unknown"),
        ({"conflict_passed": "false"}, "unknown"),
        ({}, "unknown"),
        (None, "unknown"),
    ],
)
def test_conflict_gate_only_never_overall_mergeability_or_ci(invoke, gates, expected):
    detail = {**ROW, "mergeable": True, "can_merge_check": False, "mergeable_state": gates}
    result = invoke(["-c"], ("", PAGE, 200, [ROW]), ("/7", {}, 200, detail))
    assert result.exit_code == 0, result.output
    assert result.output.endswith(f"#7\topen\tFirst\tconflict check: {expected}\n")
    assert "first page only" in result.output and "GitCode API approximation" in result.output


@pytest.mark.parametrize("title", [None, "Changed", "Changed\nconflict check: passed\x1b[31m"])
def test_detail_may_omit_or_update_display_title(invoke, title):
    # Official detail example omits title; head repositories may also be forks.
    detail = {
        "number": 7,
        "id": 107,
        "state": "open",
        "base": {"repo": {"path": "r", "namespace": {"path": "o"}, "html_url": "https://gitcode.com/o/r"}},
        "head": {"repo": {"full_name": "fork/r"}},
        "mergeable_state": {"merge_request_id": 107, "conflict_passed": False},
    }
    if title is not None:
        detail["title"] = title
    result = invoke(["-c"], ("", PAGE, 200, [ROW]), ("/7", {}, 200, detail))
    assert result.exit_code == 0, result.output
    assert len(result.output.splitlines()) == 2 and "\x1b" not in result.output
    assert ("First" if title is None else "Changed") in result.output
    assert result.output.endswith("conflict check: not passed\n")


@pytest.mark.parametrize(
    "detail",
    [
        None,
        {},
        {**ROW, "number": True},
        {**ROW, "number": 8},
        {**ROW, "id": 108},
        {**ROW, "base": {"repo": {"full_name": "other/r"}}},
        {**ROW, "base": {"repo": {"full_path": "other/r"}}},
        {**ROW, "base": {"repo": {"namespace": {"path": "other"}}}},
        {**ROW, "base": {"repo": {"path": "other"}}},
        {**ROW, "base": {"repo": {"html_url": "https://gitcode.com/other/r"}}},
        {**ROW, "base": {"repo": {"html_url": "https://[malformed"}}},
        {**ROW, "base": {"repo": {"html_url": 77}}},
        {**ROW, "base": {"repo": "other/r"}},
        {**ROW, "state": "closed"},
        {**ROW, "mergeable_state": {"conflict_passed": True, "merge_request_id": 108}},
    ],
)
def test_unverifiable_detail_no_report(invoke, detail):
    result = invoke(["-c"], ("", PAGE, 200, [ROW]), ("/7", {}, 200, detail))
    assert result.exit_code == 1 and "Open pull requests in" not in result.output


@pytest.mark.parametrize("rows", [None, {}, [ROW] * 21, [None], [{"id": 7}], [{**ROW, "number": True}]])
def test_bad_or_oversized_page_never_fans_out(invoke, rows):
    result = invoke(["-c"], ("", PAGE, 200, rows))
    assert result.exit_code == 1 and "Open pull requests in" not in result.output


def test_duplicate_row_is_not_fetched_twice(invoke):
    result = invoke(["-c"], ("", PAGE, 200, [ROW, ROW]), ("/7", {}, 200, ROW))
    assert result.exit_code == 1 and "unique" in result.output and "Open pull requests in" not in result.output


def test_later_detail_failure_does_not_publish_partial_report_or_retry(invoke):
    second = {**ROW, "number": 8, "id": 108, "title": "Second"}
    result = invoke(["--conflict-status"], ("", PAGE, 200, [ROW, second]), ("/7", {}, 200, ROW), ("/8", {}, 403, {}))
    assert result.exit_code == 1 and "error:" in result.output
    assert "Open pull requests in" not in result.output and "#7" not in result.output


def test_empty_page_reads_no_detail(invoke):
    result = invoke(["--conflict-status"], ("", PAGE, 200, []))
    assert result.exit_code == 0 and "No open pull requests" in result.output


@pytest.mark.parametrize("flags", [[], ["-c"], ["--json", "number"]])
def test_repository_status_never_proxied_as_gh_personal_status(flags):
    with pytest.raises(ProxyError, match="not supported"):
        validate_gitcode_command(["pr", "status", *flags])
