"""Offline, read-only command contract for the GitCode repository conflict view."""

from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.gh_proxy import ProxyError, dispatch

TOKEN = "status-contract-synthetic"
BASE = "https://conflict.invalid/api/v5/"
PREFIX = "/api/v5/repos/o/r/pulls"
PAGE = {"state": "open", "page": "1", "per_page": "20"}
ROW = {"number": 7, "id": 107, "state": "open", "title": "First"}


@pytest.fixture
def invoke(monkeypatch):
    # Click 8.1 mixes stderr into stdout unless separation is requested.
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))

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
            result = runner.invoke(main, ["--token", TOKEN, "-R", "o/r", "pr", "status", *args])
        assert next(steps, None) is None
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert TOKEN not in result.stdout and TOKEN not in result.stderr
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


@pytest.mark.parametrize("url", ["https://gitcode.com/o/r", "https://gitcode.com/o/r.git"])
def test_same_repository_web_and_clone_urls_preserve_conflict_check(invoke, url):
    base = {"repo": {"path": "r", "namespace": {"path": "o"}, "full_name": "o/r", "html_url": url}}
    row = {**ROW, "base": base}
    detail = {**row, "mergeable_state": {"merge_request_id": 107, "conflict_passed": False}}
    result = invoke(["-c", "--page", "2"], ("", {**PAGE, "page": "2"}, 200, [row]), ("/7", {}, 200, detail))
    assert result.exit_code == 0, result.output
    assert "page 2 only" in result.stdout and result.stdout.endswith("conflict check: not passed\n")


@pytest.mark.parametrize(
    "url",
    [
        "https://gitcode.com/other/r.git",
        "https://gitcode.com/o/other.git",
        "https://gitcode.com.evil.invalid/o/r.git",
        "https://evil.invalid@gitcode.com/o/r.git",
        "https://gitcode.com:443/o/r.git",
        "http://gitcode.com/o/r.git",
        "https://gitcode.com/o/r.git/",
        "https://gitcode.com/o/r.git.git",
        "https://gitcode.com/o/r%2Egit",
        "https://gitcode.com/o/r.git?",
        "https://gitcode.com/o/r.git#branch",
        "https://gitcode.com/o/r.gi\nt",
    ],
)
def test_noncanonical_clone_url_cannot_verify_repository_before_fanout(invoke, url):
    row = {**ROW, "base": {"repo": {"full_name": "o/r", "html_url": url}}}
    result = invoke(["-c"], ("", PAGE, 200, [row]))
    assert result.exit_code == 1 and not result.stdout
    assert "Cannot verify" in result.stderr


def test_valid_clone_url_cannot_override_conflicting_base_identity(invoke):
    detail = {**ROW, "base": {"repo": {"full_name": "other/r", "html_url": "https://gitcode.com/o/r.git"}}}
    result = invoke(["-c"], ("", PAGE, 200, [ROW]), ("/7", {}, 200, detail))
    assert result.exit_code == 1 and not result.stdout
    assert "Cannot verify" in result.stderr


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
    assert result.exit_code == 1 and "unique" in result.stderr and not result.stdout


def test_later_detail_failure_does_not_publish_partial_report_or_retry(invoke):
    second = {**ROW, "number": 8, "id": 108, "title": "Second"}
    result = invoke(["--conflict-status"], ("", PAGE, 200, [ROW, second]), ("/7", {}, 200, ROW), ("/8", {}, 403, {}))
    assert result.exit_code == 1 and "error:" in result.stderr
    assert not result.stdout and "#7" not in result.stderr


def test_empty_page_reads_no_detail(invoke):
    result = invoke(["--conflict-status"], ("", PAGE, 200, []))
    assert result.exit_code == 0 and "No open pull requests" in result.output


def test_explicit_page_reads_only_that_page_and_bounds_fanout(invoke):
    rows = [{**ROW, "number": n, "id": n + 100, "title": f"PR {n}"} for n in range(21, 41)]
    details = [(f"/{r['number']}", {}, 200, {**r, "mergeable_state": {"conflict_passed": False}}) for r in rows]
    result = invoke(["-c", "--page", "2"], ("", {**PAGE, "page": "2"}, 200, rows), *details)
    assert result.exit_code == 0, result.output
    assert "page 2 only" in result.output and "first page" not in result.output
    assert result.output.count("conflict check: not passed") == 20
    assert "#40\topen\tPR 40" in result.output


def test_empty_later_page_does_not_claim_empty_repository(invoke):
    result = invoke(["-c", "--page=3"], ("", {**PAGE, "page": "3"}, 200, []))
    assert result.exit_code == 0, result.output
    assert "No open pull requests on page 3" in result.output


@pytest.mark.parametrize("args", [["--page", "1"], ["-c", "--page", "0"], ["-c", "--page", "-1"]])
def test_invalid_page_usage_never_reads(invoke, args):
    result = invoke(args)
    assert result.exit_code == 2
    assert "--page" in result.stderr


@pytest.mark.parametrize("target", ["other/r", "github.com/o/r", ""])
def test_page_rejects_conflicting_or_empty_explicit_repository_before_io(invoke, target):
    result = invoke(["-c", "--page", "2", "-R", target])
    assert result.exit_code != 0 and "Open pull requests in" not in result.output


def test_same_repository_can_be_repeated_for_explicit_page(invoke):
    result = invoke(["-c", "--page", "2", "-R", "gitcode.com/o/r"], ("", {**PAGE, "page": "2"}, 200, []))
    assert result.exit_code == 0, result.output


def test_later_page_changed_target_discards_entire_report(invoke):
    other = {**ROW, "number": 8, "id": 108}
    result = invoke(
        ["--page", "2", "-c"],
        ("", {**PAGE, "page": "2"}, 200, [ROW, other]),
        ("/7", {}, 200, ROW),
        ("/8", {}, 200, {**other, "base": {"repo": {"full_name": "other/r"}}}),
    )
    assert result.exit_code == 1 and "Open pull requests in" not in result.output


def test_later_page_preserves_unknown_on_missing_gate(invoke):
    result = invoke(["--page", "2", "-c"], ("", {**PAGE, "page": "2"}, 200, [ROW]), ("/7", {}, 200, ROW))
    assert result.exit_code == 0, result.output
    assert result.output.endswith("conflict check: unknown\n")


@pytest.mark.parametrize("flags", [[], ["-c"], ["-c", "--page", "2"], ["--json", "number"]])
def test_repository_status_never_proxied_as_gh_personal_status(monkeypatch, flags):
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("must not fall back to native gh"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("neither backend may run"))
    with pytest.raises(ProxyError, match="use gc pr status directly") as exc:
        dispatch(["pr", "status", *flags], {"GC_GH_TARGET": "gitcode"})
    assert "refusing to fall back" in str(exc.value)
