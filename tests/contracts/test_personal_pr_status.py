"""Strict offline contract for fixed-origin, bearer-only personal status and target lookup."""

from __future__ import annotations

import gzip
import inspect
import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import personal_pr_status as personal
from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, dispatch

TOKEN = "synthetic-personal-status"
SCOPES = ("created_by_me", "assigned_to_me", "need_my_approve", "need_my_review")


def metadata(path="org/project", repo_id=501, **change):
    owner, name = path.split("/")
    return {
        "id": repo_id,
        "full_name": path,
        "path": name,
        "namespace": {"path": owner, "name": "Display namespace"},
        "human_name": "Display name",
        "owner": {"login": "different-owner"},
        **change,
    }


def row(number=7, owner="org", name="project", repo_id=501, **override):
    path = f"{owner}/{name}"
    repo = {"full_path": path, "full_name": path, "path": name}
    if repo_id is not None:
        repo["id"] = repo_id
    return {
        "number": number,
        "iid": number,
        "title": f"Change {number}",
        "state": "open",
        "base": {"repo": repo},
        "head": {"repo": {"full_path": "fork/project"}},
        "assignees": [{"email": "private@example.invalid"}],
        "body": "private description",
        **override,
    }


@pytest.fixture
def invoke(monkeypatch, tmp_config_dir):
    monkeypatch.delenv("GC_TOKEN", raising=False)

    def run(args, pages=(), *, lookup=None, scope="created_by_me", token=TOKEN, global_args=()):
        requests = []

        def respond(req):
            requests.append(req)
            assert req.method == "GET" and req.url.host == "api.gitcode.com" and req.url.scheme == "https"
            assert not req.content and TOKEN not in str(req.url)
            assert req.headers["authorization"] == f"Bearer {token}"
            assert req.headers["accept-encoding"] == "identity"
            assert not {"cookie", "private-token"} & set(req.headers)
            if lookup is not None and len(requests) == 1:
                path, reply = lookup
                assert req.url.raw_path == ("/api/v5/repos/" + path).encode()
                assert not req.url.query
            else:
                page = len(requests) - (lookup is not None)
                assert req.url.path == "/api/v5/user/pulls"
                assert sorted(req.url.params.multi_items()) == sorted(
                    {"scope": scope, "state": "open", "per_page": "100", "page": str(page)}.items()
                )
                assert 1 <= page <= len(pages), "unexpected extra queue request"
                reply = pages[page - 1]
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=reply, headers={"set-cookie": "do_not_persist=private"})

        def client():
            assert pages or lookup is not None, "must not create a client"
            return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False, trust_env=False)

        monkeypatch.setattr(personal, "open_client", client)
        options = ["--token", token] if token else []
        runner = CliRunner(mix_stderr=False) if "mix_stderr" in inspect.signature(CliRunner).parameters else CliRunner()
        result = runner.invoke(main, [*options, *global_args, "pr", "status", *args])
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert len(requests) == len(pages) + (lookup is not None)
        return result

    return run


@pytest.mark.parametrize("scope", SCOPES)
def test_one_explicit_account_queue_only_no_origin_or_me_lookup(invoke, monkeypatch, scope):
    monkeypatch.setattr("gitcode_cli.commands.pr.resolve_repo", lambda *_: pytest.fail("unexpected repository lookup"))
    result = invoke(["--scope", scope], [[row(repo_id=None), row(owner="fork", repo_id=None)], []], scope=scope)
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        f"Open pull requests across repositories (GitCode scope: {scope})",
        "  org/project#7\tChange 7",
        "  fork/project#7\tChange 7",
    ]


def test_unscoped_rows_still_ignore_unpublished_namespace_and_do_not_require_repo_id(invoke):
    repo = {"full_path": "org/project", "namespace": None}
    result = invoke(["--scope", SCOPES[0]], [[row(base={"repo": repo})], []])
    assert result.exit_code == 0 and "org/project#7" in result.output


@pytest.mark.parametrize("global_repo", [False, True])
def test_repo_filter_uses_exact_base_not_fork_or_bare_number(invoke, global_repo):
    args, options = ["--scope", SCOPES[0]], ["-R", "gitcode.com/fork/project"]
    result = invoke(
        args if global_repo else args + options,
        [
            [row(), row(owner="unrelated", repo_id=502)],
            [row(owner="fork", repo_id=503, title="One\nline\x1b\u202e " + TOKEN)],
            [],
        ],
        lookup=("fork/project", metadata("fork/project", 503)),
        global_args=options if global_repo else (),
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "Open pull requests in fork/project (GitCode scope: created_by_me)",
        r"  fork/project#7" + "\t" + r"One\nline\x1b\u202e [REDACTED]",
    ]


def test_empty_after_filtering_is_distinct_from_failure(invoke):
    result = invoke(
        ["--scope", SCOPES[0], "-R", "absent/project"],
        [[row()], []],
        lookup=("absent/project", metadata("absent/project", 502)),
    )
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
    result = invoke(["--scope", SCOPES[0], "-R", "org/project"], [[row()], bad], lookup=("org/project", metadata()))
    assert result.exit_code == 1
    assert "error:" in result.stderr
    for private in (TOKEN, "private description", "org/project", "Change 7", "Open pull requests", "No open pull"):
        assert private not in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "args,token",
    [
        (["--scope", "reviewer"], TOKEN),
        (["--scope", SCOPES[0], "-c"], TOKEN),
        (["--scope", SCOPES[0], "--page", "2"], TOKEN),
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
    assert result.exit_code != 0 and "Conflicting repository selectors" in result.stderr


def test_page_and_combined_byte_caps_fail_closed(invoke, monkeypatch):
    monkeypatch.setattr(personal, "MAX_DATA_PAGES", 1)
    args = ["--scope", SCOPES[0]]
    result = invoke(args, [[row()], [row(number=8)]])
    assert result.exit_code == 1 and "pagination limit" in result.stderr
    assert "Change 7" not in result.output
    raw = json.dumps([row()]).encode()
    monkeypatch.setattr(personal, "MAX_BYTES", len(raw) + 1)
    result = invoke(args, [httpx.Response(200, content=raw), []])
    assert result.exit_code == 1 and "byte limit" in result.stderr and "Change 7" not in result.output


@pytest.mark.parametrize("target", ["Ascend/msinsight", "ascend/msinsight", "Ascend/MSInsight"])
def test_lookup_reconciles_public_case_variants_using_canonical_path_and_id(invoke, target):
    canonical = "Ascend/msinsight"
    repo_id = 8492996
    legitimate = row(owner="Ascend", name="msinsight", repo_id=repo_id, project_id=repo_id)
    unrelated = row(owner="elsewhere", name="msinsight", repo_id=999, project_id=999)
    result = invoke(
        ["--scope", SCOPES[2], "-R", target],
        [[legitimate, unrelated], []],
        scope=SCOPES[2],
        lookup=(target, metadata(canonical, repo_id)),
    )
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "Open pull requests in Ascend/msinsight (GitCode scope: need_my_approve)",
        "  Ascend/msinsight#7\tChange 7",
    ]


@pytest.mark.parametrize(
    "item",
    [
        row(number=8, repo_id=None, project_id=501),
        row(number=8, repo_id=502),
        row(number=8, owner="other", repo_id=501),
        row(number=8, owner="Org", repo_id=501),
        row(number=8, owner="Org", repo_id=502),
        row(number=8, owner="other", repo_id=None),
        row(number=8, owner="other", repo_id=502, project_id=501),
    ],
)
def test_excluded_rows_with_ambiguous_identity_abort_entire_report(invoke, item):
    result = invoke(["--scope", SCOPES[0], "-R", "org/project"], [[row()], [item]], lookup=("org/project", metadata()))
    assert result.exit_code == 1 and "Change 7" not in result.output and "Open pull requests" not in result.output


def test_row_identity_conflicts_across_unrelated_results_are_not_reported_as_empty(invoke):
    entries = [row(owner="other", repo_id=502), row(number=8, owner="other", repo_id=503)]
    result = invoke(["--scope", SCOPES[0], "-R", "org/project"], [entries], lookup=("org/project", metadata()))
    assert result.exit_code == 1 and "No open pull" not in result.output


@pytest.mark.parametrize(
    "reply",
    [
        [],
        {},
        metadata(repo_id=True),
        metadata(repo_id="501"),
        metadata(repo_id=501.0),
        metadata(repo_id=0),
        metadata(full_name=None),
        metadata(full_name="org/%70roject"),
        metadata(full_name="org/pr\noject"),
        metadata(full_name="org/.."),
        metadata(full_name=f"{TOKEN}/project"),
        metadata("unrelated/project"),
        {**metadata(), "path": "org/project"},
        metadata(full_path="other/project"),
        metadata(namespace={"path": "other"}),
        metadata(namespace="org"),
        httpx.Response(200, content=b'{"id":501,"id":502,"full_name":"org/project"}'),
        httpx.Response(200, content=gzip.compress(b"{}"), headers={"content-encoding": "gzip"}),
        httpx.Response(302, headers={"location": "https://other.invalid"}),
        httpx.Response(404, json={"message": TOKEN}),
        httpx.Response(403, json={"message": TOKEN}),
        httpx.ConnectError(f"server error: {TOKEN}"),
    ],
)
def test_invalid_lookup_stops_before_reading_queue(invoke, reply):
    result = invoke(["--scope", SCOPES[0], "-R", "org/project"], lookup=("org/project", reply))
    assert result.exit_code == 1
    assert TOKEN not in (result.stdout + result.stderr)
    assert "Open pull requests" not in result.stdout


def test_lookup_quotes_segments_without_sending_encoded_token(invoke):
    result = invoke(
        ["--scope", SCOPES[0], "-R", "org/仓库"], [[]], lookup=("org/%E4%BB%93%E5%BA%93", metadata("org/仓库"))
    )
    assert result.exit_code == 0 and "in org/仓库" in result.output
    result = invoke(["--scope", SCOPES[0], "-R", "org/仓库"], token="%E4%BB%93%E5%BA%93")
    assert result.exit_code == 1 and "%E4%BB%93%E5%BA%93" not in (result.stdout + result.stderr)


def test_metadata_size_capped_and_charged_to_shared_budget(invoke, monkeypatch):
    args = ["--scope", SCOPES[0], "-R", "org/project"]
    data = json.dumps(metadata()).encode()
    lookup = ("org/project", httpx.Response(200, content=data))
    monkeypatch.setattr(personal, "MAX_REPO_BYTES", len(data) - 1)
    result = invoke(args, lookup=lookup)
    assert result.exit_code == 1 and "byte limit" in result.stderr
    monkeypatch.setattr(personal, "MAX_REPO_BYTES", len(data))
    monkeypatch.setattr(personal, "MAX_BYTES", len(data) + 1)
    result = invoke(args, [[]], lookup=("org/project", httpx.Response(200, content=data)))
    assert result.exit_code == 1 and "byte limit" in result.stderr and "No open pull" not in result.output


def test_proxy_still_declines_personal_extension(monkeypatch):
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("must not dispatch"))
    with pytest.raises(ProxyError, match="use gc pr status directly"):
        dispatch(["pr", "status", "--scope", SCOPES[0]], {"GC_GH_TARGET": "gitcode"})
