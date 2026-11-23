"""Direct CLI and proxy evidence with synthetic credentials and a strict HTTP transport."""

import json
import os
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.adapters import IssueAdapter
from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError, NetworkError
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command
from gitcode_cli.services import IssueService, UserService, issue_status

TOKEN = "offline-test-issue-status-token"
TARGET = {"id": 42, "full_name": "Owner/Repo", "path": "Repo", "namespace": {"path": "Owner"}}
ME = {"id": "u123", "login": "alice", "name": "Wrong Display Name"}
PUBLIC_ACTOR = {"id": "1" * 24, "object_id": "1" * 24, "login": "public-user", "name": "Display Person"}
PUBLIC_REPOSITORY = {"id": 42, "full_name": "Owner/Repo", "path": "Repo", "name": "Display Repository"}
ROW = {
    "id": 100,
    "number": "7",
    "title": "Assigned",
    "state": "opened",
    "repository": {**TARGET, "full_name": "Owner / Repo"},
    "assignee": ME,
    "user": ME,
    "html_url": "https://api.gitcode.com/Owner/Repo/issues/7",
    "created_at": "2026-01-12",
    "labels": [{"name": "bug"}],
    "body": "Never render raw content",
}
OTHER = {"id": "u456", "login": "bob"}
URI = "/repos/Owner/Repo/issues"
METADATA = ("/repos/owner/repo", {}, TARGET)
USER = ("/user", {}, ME)


def page(kind, n, payload):
    return (
        URI,
        {
            kind: ME["id"] if kind == "assignee" else ME["login"],
            "state": "open",
            "per_page": str(issue_status.PAGE_SIZE),
            "page": str(n),
        },
        payload,
    )


@pytest.fixture
def run(monkeypatch):
    client_type = httpx.Client

    def invoke(args, *steps, global_repo="owner/repo"):
        pending = iter(steps)

        def respond(request):
            path, params, payload = next(pending)
            assert request.method == "GET" and not request.content
            assert request.url.host == "issue-status.invalid" and request.url.path == "/api/v5" + path
            assert dict(request.url.params) == params and TOKEN not in str(request.url)
            assert request.headers["authorization"] == f"Bearer {TOKEN}"
            assert "cookie" not in request.headers and "private-token" not in request.headers
            return payload if isinstance(payload, httpx.Response) else httpx.Response(200, json=payload)

        def new(**kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
            return client_type(transport=httpx.MockTransport(respond), **kwargs)

        monkeypatch.setattr("gitcode_cli.repo_read.BASE_URL", "https://issue-status.invalid/api/v5/")
        monkeypatch.setattr("gitcode_cli.repo_read.httpx.Client", new)
        options = [] if global_repo is None else ["-R", global_repo]
        result = CliRunner().invoke(main, ["--token", TOKEN, *options, *args])
        assert next(pending, None) is None
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert TOKEN not in result.output
        return result

    return invoke


@pytest.mark.parametrize(
    "args",
    [[], ["--json", "assigned,createdBy,mentioned"], ["--jq", ".assigned[].title"], ["--template", "{{.assigned}}"]],
)
def test_verified_queues_native_formats_and_null_mentions(run, args):
    second = {**ROW, "id": 101, "number": 8, "title": "Created", "html_url": "https://gitcode.com/Owner/Repo/issues/8"}
    result = run(
        ["issue", "status", *args],
        METADATA,
        USER,
        page("assignee", 1, [ROW]),
        page("assignee", 2, []),
        page("creator", 1, [second]),
        page("creator", 2, []),
    )
    assert result.exit_code == 0, result.output
    assert "Never render" not in result.output
    if not args:
        assert "Mentions are unavailable" in result.output and "#7  OPENED  Assigned  bug" in result.output
    elif args[0] == "--json":
        data = json.loads(result.output)
        assert data["mentioned"] is None
        assert [a["title"] for a in data["assigned"]] == ["Assigned"]
        assert [a["title"] for a in data["createdBy"]] == ["Created"]
    elif args[0] == "--jq":
        assert result.output == '"Assigned"\n'
    else:
        assert "Assigned" in result.output and "number" in result.output


def test_observed_public_row_shape_with_canonical_metadata_and_no_assignee(run):
    # Minimal synthetic values model the public GitCode list schema: the
    # nested repository has no namespace, the creator has an opaque object ID
    # and the assignment fields can be absent or empty on an authored issue.
    metadata = {
        **PUBLIC_REPOSITORY,
        "full_name": "Display Organization / Display Repository",
        "namespace": {"full_path": "Owner"},
    }
    item = {
        **ROW,
        "state": "open",
        "user": PUBLIC_ACTOR,
        "repository": PUBLIC_REPOSITORY,
        "html_url": "https://gitcode.com/Owner/Repo/issues/7",
        "assignees": [],
    }
    del item["assignee"]
    result = run(
        ["issue", "status", "--json", "createdBy,mentioned"],
        (METADATA[0], {}, metadata),
        ("/user", {}, {"id": PUBLIC_ACTOR["id"], "login": PUBLIC_ACTOR["login"]}),
        (URI, {**page("assignee", 1, [])[1], "assignee": PUBLIC_ACTOR["id"]}, []),
        (URI, {**page("creator", 1, [])[1], "creator": PUBLIC_ACTOR["login"]}, [item]),
        (URI, {**page("creator", 2, [])[1], "creator": PUBLIC_ACTOR["login"]}, []),
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["createdBy"][0]["number"] == "7"
    assert data["mentioned"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"repository": {**TARGET, "id": 3}},
        {"repository": {**TARGET, "full_name": "Another/Repo"}},
        {"repository": {**TARGET, "path": "other"}},
        {"repository": None},
        {"repository": {**TARGET, "id": True}},
        {"repository": {**TARGET, "path_with_namespace": "other/repo"}},
        {"repository": {**TARGET, "namespace": {"path": "Owner", "full_path": "Other"}}},
        {"repository": {**TARGET, "full_name": "Display Owner / Display Repo", "namespace": None}},
        {"id": None},
        {"number": False},
        {"state": "closed"},
        {"html_url": "https://gitcode.com/Other/Repo/issues/7"},
        {"html_url": "https://gitcode.com/Owner/Repo/issues/9"},
        {"assignee": OTHER},
        {"assignee": {**ME, "id": OTHER["id"]}},
        {"assignee": None},
        {"assignees": ["unverifiable"]},
        {"assignees": [{**ME, "login": "mismatch"}]},
        {"labels": "invalid"},
    ],
)
def test_cross_repository_same_number_wrong_actor_and_malformed_data_never_print(run, override):
    result = run(
        ["issue", "status", "--json", "assigned,createdBy"],
        METADATA,
        USER,
        page("assignee", 1, [{**ROW, **override, "title": "Private foreign title"}]),
    )
    assert result.exit_code == 1 and "Private foreign title" not in result.output


@pytest.mark.parametrize("bad", [[], None, {"login": "alice"}, {"id": "u123", "name": "alice"}, {**ME, "login": "a/b"}])
def test_unverified_current_user_never_lists_issues(run, bad):
    result = run(["issue", "status"], METADATA, ("/user", {}, bad))
    assert result.exit_code == 1


def test_second_queue_can_fail_without_exposing_collected_first_queue(run):
    result = run(
        ["issue", "status"],
        METADATA,
        USER,
        page("assignee", 1, [ROW]),
        page("assignee", 2, []),
        page("creator", 1, [{**ROW, "user": OTHER}]),
    )
    assert result.exit_code == 1 and ROW["title"] not in result.output


def test_accepts_verified_secondary_assignee_and_reads_past_short_page(run):
    row = {**ROW, "assignee": OTHER, "assignees": [OTHER, ME]}
    another = {**row, "id": 101, "number": "8", "html_url": "https://gitcode.com/Owner/Repo/issues/8"}
    result = run(
        ["issue", "status", "--json", "assigned"],
        METADATA,
        USER,
        page("assignee", 1, [row]),
        page("assignee", 2, [another]),
        page("assignee", 3, []),
        page("creator", 1, []),
    )
    assert [r["number"] for r in json.loads(result.output)["assigned"]] == ["7", "8"]


@pytest.mark.parametrize(
    "next_result",
    [
        [ROW],
        {},
        httpx.Response(429, text="Private rate-limit body"),
        httpx.Response(200, json=[], headers={"X-Next-Page": "3"}),
        httpx.Response(200, json=[], headers={"Link": '<https://other.invalid/?page=3>; rel="next"'}),
    ],
)
def test_bad_continuation_no_partial_output_or_retry(run, next_result):
    result = run(["issue", "status"], METADATA, USER, page("assignee", 1, [ROW]), page("assignee", 2, next_result))
    assert result.exit_code == 1 and "Private" not in result.output and "Assigned" not in result.output


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Next-Page": "3"},
        {"X-Next-Page": "-1"},
        {"X-Prev-Page": "1"},
        {"X-Prev-Page": "0"},
        {"X-Page": "2"},
        {"X-Per-Page": "20"},
        {"X-Total": "0"},
        {"X-Total-Pages": "0"},
        {"X-Truncated": "true"},
        {"X-Incomplete-Results": "true"},
        {"Content-Range": "items 0-0/2"},
        {"X-Next-Page": "", "Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="next"'},
        {
            "Link": "<https://other.invalid/api/v5/repos/Owner/Repo/issues?"
            'assignee=u123&state=open&page=2&per_page=50>; rel="next"'
        },
        {"Link": '</api/v5/repos/Other/Repo/issues?assignee=u123&state=open&page=2&per_page=50>; rel="next"'},
        {"Link": '<?assignee=other&state=open&page=2&per_page=50>; rel="next"'},
        {"Link": '<?assignee=u123&state=all&page=2&per_page=50>; rel="next"'},
        {"Link": '<?assignee=u123&state=open&page=3&per_page=50>; rel="next"'},
        {"Link": '<?state=open&page=2&per_page=50>; rel="next"'},
        {"Link": '<?assignee=u123&state=open&page=2&page=2&per_page=50>; rel="next"'},
        {"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="next"; rel="prev"'},
        {"Link": '<?assignee=u123&state=open&page=1&per_page=50>; rel="prev"'},
        {"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="first"'},
        {"Link": '<?assignee=other&state=open&page=1&per_page=50>; rel="first"'},
        {"Link": '<?assignee=u123&state=open&page=1&per_page=50>; rel="first"; anchor=""'},
        {"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="next"; anchor="https://foreign.invalid"'},
        {"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="last"; anchor=""'},
        {"Link": '<?creator=alice&state=open&page=2&per_page=50>; rel="last"'},
        {"Link": '</api/v5/repos/Other/Repo/issues?assignee=u123&state=open&page=2&per_page=50>; rel="last"'},
        {
            "X-Total": "1",
            "Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="last"',
        },
        {
            "X-Total-Pages": "3",
            "Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="last"',
        },
        {
            "Link": (
                '<?assignee=u123&state=open&page=2&per_page=50>; rel="next", '
                '<?assignee=u123&state=open&page=1&per_page=50>; rel="last"'
            )
        },
        [("X-Next-Page", "2"), ("X-Next-Page", "3")],
        [
            ("Link", '<?assignee=u123&state=open&page=2&per_page=50>; rel="next"'),
            ("Link", '<?assignee=u123&state=open&page=2&per_page=50>; rel="next"'),
        ],
    ],
)
def test_contradictory_nonempty_pages_never_print_or_continue(run, headers):
    result = run(
        ["issue", "status", "--json", "assigned"],
        METADATA,
        USER,
        page("assignee", 1, httpx.Response(200, json=[ROW], headers=headers)),
    )
    assert result.exit_code == 1 and "Assigned" not in result.output and "other.invalid" not in result.output


def test_consistent_continuation_metadata_is_validated_against_local_requests(run):
    second = {**ROW, "id": 101, "number": 8, "html_url": "https://gitcode.com/Owner/Repo/issues/8"}
    headers = {
        "Link": '<?per_page=50&page=2&state=open&assignee=u123>; rel="next last"; title="valid, optional"',
        "X-Next-Page": "2",
        "X-Total": "2",
        "X-Total-Pages": "2",
    }
    result = run(
        ["issue", "status", "--json", "assigned"],
        METADATA,
        USER,
        page("assignee", 1, httpx.Response(200, json=[ROW], headers=headers)),
        page(
            "assignee",
            2,
            httpx.Response(
                200,
                json=[second],
                headers={
                    "X-Next-Page": "",
                    "X-Prev-Page": "1",
                    "Link": '<?per_page=50&page=1&state=open&assignee=u123>; rel="first prev"',
                },
            ),
        ),
        page("assignee", 3, []),
        page("creator", 1, []),
    )
    assert result.exit_code == 0
    assert len(json.loads(result.output)["assigned"]) == 2


@pytest.mark.parametrize("headers", [{"X-Total": "2"}, {"X-Total-Pages": "2"}, {"X-Next-Page": "2"}])
def test_empty_page_cannot_hide_incomplete_results(run, headers):
    result = run(
        ["issue", "status"],
        METADATA,
        USER,
        page("assignee", 1, httpx.Response(200, json=[ROW], headers=headers)),
        page("assignee", 2, []),
    )
    assert result.exit_code == 1 and "Assigned" not in result.output


@pytest.mark.parametrize("items", [[], [ROW]])
def test_last_link_requires_reaching_last_page_without_following_link(run, items):
    first = httpx.Response(
        200, json=items, headers={"Link": '<?assignee=u123&state=open&page=3&per_page=50>; rel="last"'}
    )
    remaining = [page("assignee", 2, [])] if items else []
    result = run(["issue", "status"], METADATA, USER, page("assignee", 1, first), *remaining)
    assert result.exit_code == 1 and "Assigned" not in result.output


def test_last_link_cannot_change_on_a_following_page(run):
    first = httpx.Response(
        200, json=[ROW], headers={"Link": '<?assignee=u123&state=open&page=3&per_page=50>; rel="last"'}
    )
    second = httpx.Response(
        200,
        json=[{**ROW, "id": 101, "number": 8, "html_url": "https://gitcode.com/Owner/Repo/issues/8"}],
        headers={"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="last"'},
    )
    result = run(["issue", "status"], METADATA, USER, page("assignee", 1, first), page("assignee", 2, second))
    assert result.exit_code == 1 and "Assigned" not in result.output


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Prev-Page": ""},
        {"X-Prev-Page": "2"},
        {"Link": '<?assignee=u123&state=open&page=2&per_page=50>; rel="prev"'},
        {"Link": '<?creator=alice&state=open&page=1&per_page=50>; rel="prev"'},
        {
            "Link": '<?assignee=u123&state=open&page=1&per_page=50>; rel="prev"; anchor=""',
            "X-Prev-Page": "1",
        },
        {
            "Link": '<?assignee=u123&state=open&page=1&per_page=50>; rel="prev"',
            "X-Prev-Page": "2",
        },
        [("X-Prev-Page", "1"), ("X-Prev-Page", "2")],
    ],
)
def test_subsequent_page_rejects_conflicting_previous_hints(run, headers):
    result = run(
        ["issue", "status"],
        METADATA,
        USER,
        page("assignee", 1, [ROW]),
        page("assignee", 2, httpx.Response(200, json=[], headers=headers)),
    )
    assert result.exit_code == 1 and "Assigned" not in result.output


def test_data_after_end_header_is_not_a_complete_report(run):
    result = run(
        ["issue", "status"],
        METADATA,
        USER,
        page("assignee", 1, httpx.Response(200, json=[ROW], headers={"X-Next-Page": ""})),
        page("assignee", 2, [{**ROW, "id": 101, "number": 8, "html_url": "https://gitcode.com/Owner/Repo/issues/8"}]),
    )
    assert result.exit_code == 1 and "Assigned" not in result.output


def test_unexhausted_page_limit_fails_without_partial_results(run, monkeypatch):
    monkeypatch.setattr(issue_status, "MAX_DATA_PAGES", 1)
    result = run(["issue", "status"], METADATA, USER, page("assignee", 1, [ROW]), page("assignee", 2, [ROW]))
    assert result.exit_code == 1 and "page limit" in result.output and "Assigned" not in result.output


def test_null_mentions_is_not_an_empty_result(run):
    result = run(
        ["issue", "status", "--json", "mentioned"], METADATA, USER, page("assignee", 1, []), page("creator", 1, [])
    )
    assert json.loads(result.output) == {"mentioned": None}


def test_safe_display_and_no_raw_response(run):
    result = run(
        ["issue", "status"],
        METADATA,
        USER,
        page("assignee", 1, [{**ROW, "title": TOKEN + "\x1b[31m"}]),
        page("assignee", 2, []),
        page("creator", 1, []),
    )
    assert result.exit_code == 0 and "[REDACTED]" in result.output and "\x1b" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["issue", "list", "--mention", "alice"],
        ["issue", "list", "--web", "--mention", "@me"],
        ["issue", "status", "--json", "unknown"],
        ["issue", "status", "-R", "other/repo"],
    ],
)
def test_refusal_before_network(run, args):
    assert run(args).exit_code != 0


@pytest.mark.parametrize(
    "origin",
    [
        "https://gitcode.com:8443/owner/repo",
        "https://gitcode.com.example/owner/repo",
        "https://some-user@gitcode.com/owner/repo",
        "ssh://git@ssh.gitcode.com:2222/owner/repo",
        "git@gitcode.com.example:owner/repo",
    ],
)
def test_untrusted_origin_refused_but_explicit_repo_still_works(run, monkeypatch, origin):
    calls = []

    def local_git(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=origin)

    monkeypatch.setattr("gitcode_cli.repo_read.subprocess.run", local_git)
    assert "exact GitCode origin" in run(["issue", "status"], global_repo=None).output
    result = run(
        ["issue", "status", "-R", "owner/repo"],
        METADATA,
        USER,
        page("assignee", 1, []),
        page("creator", 1, []),
        global_repo=None,
    )
    assert result.exit_code == 0 and len(calls) == 1


def test_canonical_gitcode_origin_can_select_repository(run, monkeypatch):
    monkeypatch.setattr(
        "gitcode_cli.repo_read.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="ssh://git@ssh.gitcode.com:443/owner/repo.git\n"),
    )
    result = run(["issue", "status"], METADATA, USER, page("assignee", 1, []), page("creator", 1, []), global_repo=None)
    assert result.exit_code == 0


@pytest.mark.parametrize("second", ["https://gitcode.com/owner/repo.git", "https://gitcode.com/other/repo.git"])
def test_ambiguous_gitcode_origin_requires_explicit_repo(run, monkeypatch, tmp_path, second):
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.chdir(tmp_path)

    def local_git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout

    first = "https://gitcode.com/owner/repo.git"
    local_git("init", "--quiet", "--template=")
    local_git("remote", "add", "origin", first)
    local_git("config", "--local", "--add", "remote.origin.url", second)
    assert local_git("remote", "get-url", "--all", "--", "origin").splitlines() == [first, second]

    result = run(["issue", "status"], global_repo=None)
    assert result.exit_code != 0 and "exact GitCode origin" in result.output
    result = run(
        ["issue", "status", "-R", "owner/repo"],
        METADATA,
        USER,
        page("assignee", 1, []),
        page("creator", 1, []),
        global_repo=None,
    )
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("custom", [False, True])
def test_sdk_reuses_injected_transport_and_preserves_verified_status(custom, monkeypatch):
    class OptedInClient(GitCodeClient):
        def read_issue_status_page(self, endpoint, params):
            return super().read_issue_status_page(endpoint, params)

    steps = iter([METADATA, USER, page("assignee", 1, [ROW]), page("assignee", 2, []), page("creator", 1, [])])

    def handle(request):
        path, params, payload = next(steps)
        assert request.url.host == "api.gitcode.com" and request.url.path == "/api/v5" + path
        assert dict(request.url.params) == params
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers and "private-token" not in request.headers
        return httpx.Response(200, json=payload)

    client = (OptedInClient if custom else GitCodeClient)(TOKEN, transport=httpx.MockTransport(handle))
    client._client.auth = httpx.BasicAuth("old-user", "old-password")
    client._client.headers["private-token"] = "must-not-send"
    client._client.cookies.set("session", "must-not-send")
    owner = UserService(client)

    def forbid_client(*args, **kwargs):
        raise AssertionError("SDK status must not create another HTTP client")

    monkeypatch.setattr("gitcode_cli.repo_read.httpx.Client", forbid_client)
    try:
        status = IssueAdapter(IssueService(client), owner).status("owner", "repo")
        assert status.approximated and status.item["mentioned"] is None
        assert status.item["assigned"][0]["number"] == "7"
        assert next(steps, None) is None and not client._client.is_closed
    finally:
        client.close()


def test_sdk_rejects_custom_scope_change():
    class ChangedScope(GitCodeClient):
        def read_issue_status_page(self, endpoint, params):
            params["state"] = "all"
            return TARGET, httpx.Headers(), httpx.URL(f"https://api.gitcode.com/api/v5{endpoint}", params=params)

    def forbid_request(request):
        raise AssertionError("This test must not send any request")

    client = ChangedScope(TOKEN, transport=httpx.MockTransport(forbid_request))
    try:
        with pytest.raises(APIError, match="different request scope"):
            IssueAdapter(IssueService(client)).status("owner", "repo")
    finally:
        client.close()


_SDK_QUERY = {"state": "open", "page": "1", "per_page": "50", "assignee": "u123"}


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        ("/user", {"token": "synthetic-unrelated-credential"}),
        ("/repos/owner/repo", {"private_token": "synthetic-unrelated-credential"}),
        ("/repos/owner/issues", {"state": "open"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "access_token": "synthetic-unrelated-credential"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "authorization": "synthetic-unrelated-credential"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "q": "foo"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "creator": "alice"}),
        ("/repos/owner/repo/issues", {"state": "open", "page": "1", "per_page": "50"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "assignee": "u123,u456"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "assignee": TOKEN}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "assignee": 123}),
        ("/repos/owner/repo/issues", {"state": "open", "page": "1", "per_page": "50", "creator": "@me"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "state": "all"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "page": "0"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "page": "12"}),
        ("/repos/owner/repo/issues", {**_SDK_QUERY, "per_page": "100"}),
    ],
)
def test_public_sdk_page_rejects_noncontract_queries_without_sending(endpoint, params):
    def forbid_request(request):
        raise AssertionError("The public SDK must not send out-of-contract queries")

    client = GitCodeClient(TOKEN, transport=httpx.MockTransport(forbid_request))
    try:
        with pytest.raises(APIError) as exc:
            client.read_issue_status_page(endpoint, params)
        assert TOKEN not in str(exc.value) and "synthetic-unrelated-credential" not in str(exc.value)
    finally:
        client.close()


def test_public_sdk_allows_metadata_named_issues_and_terminal_queue_probe():
    def handle(request):
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        return httpx.Response(200, json=[])

    client = GitCodeClient(TOKEN, transport=httpx.MockTransport(handle))
    try:
        assert client.read_issue_status_page("/repos/owner/issues", {})[0] == []
        assert client.read_issue_status_page("/repos/owner/repo/issues", {**_SDK_QUERY, "page": "11"})[0] == []
    finally:
        client.close()


@pytest.mark.parametrize("failure", ["redirect", "oversized", "transport"])
def test_sdk_status_does_not_follow_redirects_or_expose_failed_response(failure, monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "https://other.invalid"}, text=TOKEN)
        if failure == "oversized":
            return httpx.Response(200, text=TOKEN * 100)
        raise httpx.TransportError(TOKEN)

    if failure == "oversized":
        monkeypatch.setattr("gitcode_cli.repo_read.MAX_RESPONSE", 32)
    client = GitCodeClient(TOKEN, transport=httpx.MockTransport(handle))
    client._client.follow_redirects = True
    try:
        with pytest.raises(APIError if failure != "transport" else NetworkError) as exc_info:
            IssueAdapter(IssueService(client)).status("owner", "repo")
        assert TOKEN not in str(exc_info.value) and "other.invalid" not in str(exc_info.value)
        assert len(calls) == 1 and not client._client.is_closed
    finally:
        client.close()


@pytest.mark.parametrize(
    "args", [["issue", "status"], ["issue", "status", "--json", "assigned"], ["issue", "list", "--mention=bob"]]
)
def test_gitcode_targeted_proxy_rejects_inexact_semantics(args):
    with pytest.raises(ProxyError, match="refusing"):
        validate_gitcode_command(args)
    validate_gitcode_command(["issue", "list", "--author", "bob"])
