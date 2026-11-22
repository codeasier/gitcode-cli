"""Offline keyword search and repository-label command/REST contracts."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call
from urllib.parse import parse_qs

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext
from gitcode_cli.errors import APIError
from gitcode_cli.services.labels import LabelService
from gitcode_cli.services.search import SearchService, search_pulls


@pytest.fixture
def run(monkeypatch, tmp_config_dir):
    client = MagicMock()
    monkeypatch.setattr(AppContext, "client", lambda _: client)
    return client, lambda args, **kw: CliRunner().invoke(main, args, **kw)


def test_search_repos_across_pages(run):
    client, invoke = run
    client.get.side_effect = [
        [{"id": i, "name": f"n{i}", "full_name": f"nested/sub/n{i}"} for i in range(20)],
        [{"id": 20, "full_name": "nested/sub/n20"}, {"id": 21, "full_name": "not returned"}],
    ]
    r = invoke(
        [
            "search",
            "repos",
            "two",
            "words",
            "--language",
            "C++",
            "--owner",
            "sub",
            "--sort",
            "stars",
            "--order",
            "desc",
            "-L",
            "21",
            "--json",
            "id,fullName",
        ]
    )
    assert r.exit_code == 0, r.output
    results = json.loads(r.output)
    assert len(results) == 21
    assert results[-1] == {"id": 20, "fullName": "nested/sub/n20"}
    assert client.get.call_args_list == [
        call(
            "/search/repositories",
            params={
                "q": "two words",
                "owner": "sub",
                "language": "C++",
                "sort": "stars_count",
                "order": "desc",
                "page": page,
                "per_page": 20,
            },
        )
        for page in [1, 2]
    ]


def test_search_issues_repo_state(run):
    client, invoke = run
    client.get.return_value = [
        {
            "id": 73,
            "number": "42",
            "state": "open",
            "title": "hello",
            "repository": {"name": "repo", "full_name": "nested/repo"},
        }
    ]
    for prefix, suffix in [(["-R", "nested/repo"], []), ([], ["-R", "gitcode.com/nested/repo"])]:
        r = invoke(prefix + ["search", "issues", "hello", "--sort", "updated", "--state", "open"] + suffix)
        assert r.exit_code == 0, r.output
        assert "nested/repo\t#42\tOPEN\thello" in r.output
        client.get.assert_called_with(
            "/search/issues",
            params={
                "q": "hello",
                "repo": "nested/repo",
                "state": "open",
                "sort": "last_push_at",
                "page": 1,
                "per_page": 30,
            },
        )


def test_search_users_template(run):
    client, invoke = run
    client.get.return_value = [{"id": "u", "login": "someone", "html_url": "https://gitcode.com/someone"}]
    r = invoke(["search", "users", "some", "--sort", "joined", "--json", "login,url", "-t", "{{.login}} {{.url}}"])
    assert r.exit_code == 0, r.output
    assert "someone https://gitcode.com/someone" in r.output
    client.get.assert_called_once_with(
        "/search/users", params={"q": "some", "sort": "joined_at", "page": 1, "per_page": 30}
    )


@pytest.mark.parametrize(
    "args",
    [
        ["search", "issues", "foo", "-R", "github.com/o/r"],
        ["search", "issues", "foo", "-R", "a/b", "-R", "b/c"],
        ["search", "repos", "stars:>5"],
        ["search", "repos", "foo", "--owner", "a", "--owner", "b"],
        ["search", "users", "foo", "--json", "unknown"],
        ["search", "repos", "foo", "-L", "2001"],
        ["search", "issues", "foo", "-q", "."],
        ["search", "users", "foo", "--json", "id", "-q", ".", "-t", "{{.id}}"],
        ["-R", "a/b", "search", "users", "x"],
        ["search", "issues", "  "],
        ["search", "issues", "x", "--include-prs"],
    ],
)
def test_invalid_search_flags_never_request(run, args):
    client, invoke = run
    assert invoke(args).exit_code != 0
    client.get.assert_not_called()


@pytest.mark.parametrize("data", [{"items": []}, [{}], [3], [{"id": 1}, {"id": 1}]])
def test_search_invalid_pages(data):
    client = MagicMock()
    client.get.return_value = data
    with pytest.raises(APIError):
        SearchService(client).search("issues", "keyword", 20)


@pytest.mark.parametrize(
    ("resource", "keyword", "limit"), [("other", "x", 10), ("issues", "", 1), ("repositories", "x", 2001)]
)
def test_bounds_fail_before_get(resource, keyword, limit):
    client = MagicMock()
    with pytest.raises(ValueError):
        SearchService(client).search(resource, keyword, limit)
    client.get.assert_not_called()


def test_label_list_with_filter_beyond_first_page(run):
    client, invoke = run
    client.get.side_effect = [
        [{"name": f"unrelated{i}"} for i in range(100)],
        [{"id": 1234, "name": "My GOAL", "color": "#00AA11"}],
    ]
    r = invoke(["-R", "o/r", "label", "list", "-L", "1", "-S", "goal", "--json", "name,color"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == [{"name": "My GOAL", "color": "00AA11"}]
    assert client.get.call_args_list == [call("/repos/o/r/labels", params={"page": n, "per_page": 100}) for n in [1, 2]]


def test_label_crud_and_prompt(run):
    client, invoke = run
    client.post.return_value = {"id": 2, "name": "fix me", "color": "#aabbcc"}
    r = invoke(["label", "create", "fix me", "-R", "o/r", "-c", "aAbBcC"])
    assert r.exit_code == 0, r.output
    client.post.assert_called_once_with("/repos/o/r/labels", json={"name": "fix me", "color": "#AABBCC"})
    client.patch.return_value = {"id": 2, "name": "合入", "color": "#FFFFFF"}
    r = invoke(["label", "edit", "fix me?", "-R", "o/r", "-n", "合入", "-c", "#FFFFFF"])
    assert r.exit_code == 0, r.output
    client.patch.assert_called_once_with("/repos/o/r/labels/fix%20me%3F", params={"name": "合入", "color": "#FFFFFF"})
    args = ["label", "delete", "fix me", "-R", "o/r"]
    assert invoke(args, input="n\n").exit_code != 0
    client.delete.assert_not_called()
    client.delete.return_value = {}
    client.get.return_value = [{"id": 6, "name": "unrelated", "color": "#FFF"}]
    r = invoke(args + ["--yes"])
    assert r.exit_code == 0, r.output
    client.delete.assert_called_once_with("/repos/o/r/labels/fix%20me")


@pytest.mark.parametrize(
    "args",
    [
        ["create", ".", "-c", "ffffff"],
        ["create", "name", "-c", "GG0033"],
        ["edit", "name"],
        ["delete", "../bad", "--yes"],
        ["delete", "one,two", "--yes"],
        ["edit", "ok", "-n", "a%2Fb"],
        ["create", "name", "--description", "no support"],
        ["edit", "foo", "-n", "bar", "-R", "github.com/o/r"],
    ],
)
def test_label_invalid_args_no_mutation(run, args):
    client, invoke = run
    r = invoke(["-R", "o/r", "label", *args])
    assert r.exit_code != 0
    client.post.assert_not_called()
    client.patch.assert_not_called()
    client.delete.assert_not_called()


def test_label_wire_contract_for_form_and_query(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "labels.invalid"
        return httpx.Response(200, json={"id": 1, "name": "a b", "color": "#AABBCC"})

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: http)
        client = GitCodeClient("synthetic", base_url="https://labels.invalid/api/v5/")
        labels = LabelService(client, "o", "r")
        labels.create("a b", "#AABBCC")
        labels.edit("a?", "a b", "#AABBCC")
    create, edit = requests
    assert create.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert create.url.raw_path.split(b"?")[0] == b"/api/v5/repos/o/r/labels"
    assert parse_qs(create.content.decode()) == {"name": ["a b"], "color": ["#AABBCC"]}
    assert edit.url.raw_path.split(b"?")[0] == b"/api/v5/repos/o/r/labels/a%3F"
    assert dict(edit.url.params) == {"name": "a b", "color": "#AABBCC", "access_token": "synthetic"}
    assert edit.content == b""


@pytest.mark.parametrize("method", ["create", "edit", "delete"])
def test_uncertain_label_write_not_retried(run, method):
    client, invoke = run
    args = {"create": ["x", "-c", "eeeeee"], "edit": ["x", "-n", "y"], "delete": ["x", "--yes"]}
    method_name = {"create": "post", "edit": "patch", "delete": "delete"}[method]
    getattr(client, method_name).return_value = {"unexpected": True}
    r = invoke(["-R", "o/r", "label", method, *args[method]])
    assert r.exit_code == 1 and "Verify remote state" in r.output
    getattr(client, method_name).assert_called_once()


@pytest.mark.parametrize("force", [True, False])
def test_clone_additive_never_replaces(run, force):
    cli, invoke = run
    cli.get.side_effect = [
        [{"name": "fix", "color": "#abc"}, {"name": "help", "color": "#aabbcc"}, {"name": "same", "color": "#000000"}],
        [
            {"name": "HELP", "color": "#000"},
            {"name": "same", "color": "#000000"},
            {"name": "only-dest", "color": "#000000"},
        ],
    ]
    cli.post.return_value = {"id": 995, "name": "fix", "color": "#aabbcc"}
    cli.patch.return_value = {"id": 996, "name": "HELP", "color": "#aabbcc"}
    r = invoke(["label", "clone", "source/labels", "-R", "dest/labels", *(["--force"] if force else [])])
    assert r.exit_code == 0, r.output
    cli.post.assert_called_once_with("/repos/dest/labels/labels", json={"name": "fix", "color": "#AABBCC"})
    if force:
        assert "1 created, 1 updated, 1 kept" in r.output
        cli.patch.assert_called_once_with("/repos/dest/labels/labels/HELP", params={"color": "#AABBCC"})
    else:
        assert "1 created, 0 updated, 2 kept" in r.output
        cli.patch.assert_not_called()
    cli.put.assert_not_called()
    cli.delete.assert_not_called()


def test_preflight_entire_clone_and_conflicting_case(run):
    cli, invoke = run
    args = ["label", "clone", "source/r", "-R", "dest/r", "--force"]
    for data in [
        [[{"name": "ok", "color": "ffffff"}, {"name": "bad", "color": "not a color"}], []],
        [[{"name": "fix", "color": "aaaaaa"}], [{"name": "Fix"}, {"name": "FIX"}]],
        [[{"name": "ok", "color": "ffffff"}], {"error": True}],
    ]:
        cli.get.side_effect = data
        assert invoke(args).exit_code == 1
        cli.post.assert_not_called()
        cli.patch.assert_not_called()
    assert invoke(["label", "clone", "o/r", "-R", "O/R"]).exit_code != 0


def test_clone_partial_failure_reports_confirmed_and_stops(run):
    cli, invoke = run
    cli.get.side_effect = [[{"name": n, "color": "#fff"} for n in ["first", "second", "third"]], []]
    cli.post.side_effect = [{"id": 1, "name": "first", "color": "#FFFFFF"}, APIError("Denied")]
    r = invoke(["label", "clone", "src/r", "-R", "dest/r"])
    assert r.exit_code == 1
    assert "second" in r.output and "1 confirmed creates" in r.output
    assert cli.post.call_count == 2


@pytest.mark.parametrize(
    ("existing", "color", "action"),
    [
        ([], "ffffff", "Created"),
        ([{"name": "Fix", "color": "#000"}], "ffffff", "Updated"),
        ([{"name": "Fix", "color": "#fff"}], "ffffff", "Kept"),
        ([{"name": "Fix", "color": "#fff"}], None, "Kept"),
    ],
)
def test_create_force_preserves_omitted_fields(run, existing, color, action):
    cli, invoke = run
    cli.get.return_value = existing
    cli.post.return_value = {"id": 3, "name": "fix", "color": "#FFFFFF"}
    cli.patch.return_value = {"id": 3, "name": "Fix", "color": "#FFFFFF"}
    r = invoke(["label", "create", "fix", "-R", "o/r", "--force", *(["-c", color] if color else [])])
    assert r.exit_code == 0 and f"{action} label" in r.output
    if action == "Kept":
        cli.patch.assert_not_called()
        cli.post.assert_not_called()


def _typed_page(page, per_page, total, content):
    return {
        "page_num": page,
        "page_size": per_page,
        "total": total,
        "page_count": (total + per_page - 1) // per_page,
        "content": content,
    }


def test_search_prs_paginates_and_projects(run):
    client, invoke = run
    page1 = [{"id": str(n), "iid": n, "state": "open", "path_with_namespace": "first/repo"} for n in range(1, 11)]
    page2 = [
        {
            "id": None,
            "iid": 1,
            "state": "merged",
            "title": "update",
            "description": "PR body",
            "source_branch": "topic/a",
            "target_branch": "main",
            "comment_num": 2,
            "labels": ["ci"],
            "path_with_namespace": "second/repo",
            "url": "https://gitcode.com/second/repo/pulls/1",
            "author": {"id": 123, "username": "someone"},
        },
        {"id": "last", "state": "closed"},
    ]
    client.get.side_effect = [_typed_page(1, 10, 12, page1), _typed_page(2, 10, 12, page2)]
    r = invoke(
        [
            "search",
            "prs",
            "query",
            "--sort",
            "updated",
            "--order",
            "asc",
            "-L",
            "11",
            "--json",
            "id,number,state,title,body,repository,commentsCount,labels,headRefName,baseRefName,url,author",
        ]
    )
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    assert len(rows) == 11 and rows[0]["state"] == "OPEN"
    assert rows[-1] == {
        "id": None,
        "number": 1,
        "state": "MERGED",
        "title": "update",
        "body": "PR body",
        "headRefName": "topic/a",
        "baseRefName": "main",
        "commentsCount": 2,
        "labels": ["ci"],
        "repository": {"name": "repo", "nameWithOwner": "second/repo"},
        "url": "https://gitcode.com/second/repo/pulls/1",
        "author": {"id": 123, "login": "someone", "name": "someone", "is_bot": False},
    }
    assert client.get.call_args_list == [
        call("/search", params={"type": "pullrequest", "q": "query", "p": n, "pp": 10, "s": "updated_at", "o": "asc"})
        for n in [1, 2]
    ]


@pytest.mark.parametrize(
    "args",
    [
        ["query", "--state", "open"],
        ["query", "-R", "o/r"],
        ["repo:o/r", "query"],
        ["query", "-L", "1001"],
    ],
)
def test_pr_search_rejects_unsupported_global_filters(run, args):
    client, invoke = run
    assert invoke(["search", "prs", *args]).exit_code != 0
    client.get.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"content": []},
        _typed_page(2, 10, 0, []),
        _typed_page(1, 5, 0, []),
        _typed_page(1, 10, 1, []),
        _typed_page(1, 10, 1, [{}]),
        _typed_page(1, 10, 2, [{"id": "same"}, {"id": "same"}]),
    ],
)
def test_pr_search_fails_closed_on_untrustworthy_pages(body):
    client = MagicMock()
    client.get.return_value = body
    with pytest.raises(APIError):
        search_pulls(client, "query", 20)
    client.get.assert_called_once()


@pytest.mark.parametrize("token", ["synthetic", ""])
def test_pr_search_wire_uses_bearer_or_no_auth_on_canonical_host(monkeypatch, token):
    def handler(request):
        assert request.url.host == "api.gitcode.com"
        assert request.url.path == "/api/v5/search"
        assert dict(request.url.params) == {"type": "pullrequest", "q": "关键词+test", "p": "1", "pp": "1"}
        assert request.headers.get("authorization") == (f"Bearer {token}" if token else None)
        return httpx.Response(200, json=_typed_page(1, 1, 0, []))

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: http)
        assert search_pulls(GitCodeClient(token), "关键词+test", 1) == []


@pytest.mark.parametrize("identity", [None, 0, -1, True, "2", {}])
def test_label_confirm_requires_positive_integer_identity(run, identity):
    client, invoke = run
    client.post.return_value = {"id": identity, "name": "x", "color": "#FFFFFF"}
    r = invoke(["label", "create", "x", "-R", "o/r", "--color", "FFFFFF"])
    assert r.exit_code == 1 and "not confirmed" in r.output
    client.post.assert_called_once()


@pytest.mark.parametrize("readback", [[{"name": "X"}], {}, [{"error": "missing name"}]])
def test_label_delete_does_not_claim_success_without_absence(run, readback):
    client, invoke = run
    client.delete.return_value = {}
    client.get.return_value = readback
    r = invoke(["label", "delete", "x", "-R", "o/r", "--yes"])
    assert r.exit_code == 1 and "Verify remote state" in r.output
    assert "Deleted label" not in r.output
    client.delete.assert_called_once()
    client.get.assert_called_once()
