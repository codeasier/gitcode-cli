"""Strict offline contract: token and provider scopes travel to exactly one endpoint."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import personal_pr_status as personal
from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, dispatch

TOKEN = "synthetic-personal-status"
SCOPES = ("created_by_me", "assigned_to_me", "need_my_approve", "need_my_review")


def row(number=7, owner="org", **override):
    return {
        "number": number,
        "iid": number,
        "title": f"Change {number}",
        "state": "open",
        "base": {"repo": {"full_path": f"{owner}/project", "full_name": f"{owner}/project", "path": "project"}},
        "head": {"repo": {"full_path": "fork/project"}},
        "assignees": [{"email": "private@example.invalid"}],
        "body": "private description",
        **override,
    }


@pytest.fixture
def invoke(monkeypatch, tmp_config_dir):
    monkeypatch.delenv("GC_TOKEN", raising=False)

    def run(args, pages=(), *, scope="created_by_me", token=TOKEN, global_args=()):
        requests = []

        def respond(req):
            requests.append(req)
            page = len(requests)
            assert (req.method, str(req.url.copy_with(query=None))) == (
                "GET",
                "https://api.gitcode.com/api/v5/user/pulls",
            )
            assert sorted(req.url.params.multi_items()) == sorted(
                {"scope": scope, "state": "open", "per_page": "100", "page": str(page)}.items()
            )
            assert not req.content and TOKEN not in str(req.url)
            assert req.headers["authorization"] == f"Bearer {TOKEN}"
            assert not {"cookie", "private-token"} & set(req.headers)
            reply = pages[page - 1]
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=reply, headers={"set-cookie": "do_not_persist=private"})

        def client():
            assert pages, "must not create a client"
            return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False, trust_env=False)

        monkeypatch.setattr(personal, "open_client", client)
        options = ["--token", token] if token else []
        result = CliRunner().invoke(main, [*options, *global_args, "pr", "status", *args])
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert len(requests) == len(pages)
        return result

    return run


@pytest.mark.parametrize("scope", SCOPES)
def test_one_explicit_account_queue_only_no_origin_or_me_lookup(invoke, monkeypatch, scope):
    monkeypatch.setattr("gitcode_cli.commands.pr.resolve_repo", lambda *_: pytest.fail("unexpected repository lookup"))
    result = invoke(["--scope", scope], [[row(), row(owner="fork")], []], scope=scope)
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        f"Open pull requests across repositories (GitCode scope: {scope})",
        "  org/project#7\tChange 7",
        "  fork/project#7\tChange 7",
    ]


@pytest.mark.parametrize("global_repo", [False, True])
def test_repo_filter_uses_exact_base_not_fork_or_bare_number(invoke, global_repo):
    args, options = ["--scope", SCOPES[0]], ["-R", "gitcode.com/fork/project"]
    result = invoke(
        args if global_repo else args + options,
        [[row(), row(owner="Fork")], [row(owner="fork", title="One\nline\x1b\u202e " + TOKEN)], []],
        global_args=options if global_repo else (),
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "Open pull requests in fork/project (GitCode scope: created_by_me)",
        r"  fork/project#7" + "\t" + r"One\nline\x1b\u202e [REDACTED]",
    ]


def test_empty_after_filtering_is_distinct_from_failure(invoke):
    result = invoke(["--scope", SCOPES[0], "-R", "absent/project"], [[row()], []])
    assert result.exit_code == 0 and result.output.endswith("  No open pull requests in this scope\n")


@pytest.mark.parametrize(
    "bad",
    [
        {},
        [None],
        [row(state="closed")],
        [row(title=None)],
        [row(number=False)],
        [row(iid=True, number=1)],
        [row(iid=8)],
        [row(base=None)],
        [row(base={"repo": {"full_name": "org/project"}})],
        [row(base={"repo": {"full_path": "org/project", "full_name": "other/project"}})],
        [row(base={"repo": {"full_path": "org/project", "path": "other"}})],
        [row(base={"repo": {"full_path": "org/project", "id": 1}}, project_id=2)],
        [row(base={"repo": {"full_path": "org/project", "id": 1}}, project_id=True)],
        [row(base={"repo": {"full_path": "org/project", "id": 1.0}}, project_id=1)],
        [row(base={"repo": {"full_path": "not-a-path"}})],
        [row(base={"repo": {"full_path": "org/.."}})],
        [row(base={"repo": {"full_path": "org/proj\x1bect"}})],
        [row(base={"repo": {"full_path": "org/%70roject"}})],
        [row(base={"repo": {"full_path": f"{TOKEN}/project"}})],
        [row(number=9)] * 101,
        [row()],  # same (base, number) as the first page, regardless of title changes
        httpx.Response(200, content=b'[{"number":2,"number":3}]'),
        httpx.Response(200, headers={"content-encoding": "custom"}, content=b"[]"),
        httpx.Response(200, json=[], headers={"link": '<https://external.invalid/>; rel="next"'}),
        httpx.Response(200, json=[], headers={"x-next-page": "3"}),
        httpx.Response(401, json={"message": f"private description: {TOKEN}"}),
        httpx.Response(403),
        httpx.Response(404),
        httpx.Response(429),
        httpx.Response(500),
        httpx.Response(206, json=[]),
        httpx.Response(302, headers={"location": "https://external.invalid"}),
        httpx.ConnectError(f"private description: {TOKEN}"),
    ],
)
def test_late_unknown_never_becomes_success_partial_or_empty(invoke, bad):
    result = invoke(["--scope", SCOPES[0], "-R", "org/project"], [[row()], bad])
    assert result.exit_code == 1
    assert "error:" in result.output
    for private in (TOKEN, "private description", "org/project", "Change 7", "Open pull requests", "No open pull"):
        assert private not in result.output


@pytest.mark.parametrize(
    "args,token",
    [
        (["--scope", "reviewer"], TOKEN),
        (["--scope", SCOPES[0], "-c"], TOKEN),
        (["--scope", SCOPES[0], "--json", "number"], TOKEN),
        (["--scope", SCOPES[0], "--token", "unexpected"], TOKEN),
        (["--scope", SCOPES[0], "-R", "org/" + TOKEN], TOKEN),
        (["--scope", SCOPES[0], "-R", "github.com/org/project"], TOKEN),
        (["--scope", SCOPES[0], "-R", ""], TOKEN),
        (["--scope", SCOPES[0], "-R", "org/%70roject"], TOKEN),
        (["--scope", SCOPES[0]], None),
        (["--scope", SCOPES[0]], "token\ninvalid"),
    ],
)
def test_invalid_combinations_require_no_request(invoke, args, token):
    result = invoke(args, token=token)
    assert result.exit_code != 0 and "No open pull requests" not in result.output


def test_conflicting_explicit_targets_rejected_before_read(invoke):
    result = invoke(["--scope", SCOPES[0], "-R", "other/repo"], global_args=("-R", "org/repo"))
    assert result.exit_code != 0 and "Conflicting repository selectors" in result.output


def test_page_and_combined_byte_caps_fail_closed(invoke, monkeypatch):
    monkeypatch.setattr(personal, "MAX_DATA_PAGES", 1)
    args = ["--scope", SCOPES[0]]
    result = invoke(args, [[row()], [row(number=8)]])
    assert result.exit_code == 1 and "pagination limit" in result.output
    assert "Change 7" not in result.output
    raw = json.dumps([row()]).encode()
    monkeypatch.setattr(personal, "MAX_BYTES", len(raw) + 1)
    result = invoke(args, [httpx.Response(200, content=raw), []])
    assert result.exit_code == 1 and "byte limit" in result.output and "Change 7" not in result.output


def test_proxy_still_declines_personal_extension(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("must not dispatch"))
    with pytest.raises(ProxyError, match="use gc pr status directly"):
        dispatch(["pr", "status", "--scope", SCOPES[0]], {"GC_GH_TARGET": "gitcode"})
