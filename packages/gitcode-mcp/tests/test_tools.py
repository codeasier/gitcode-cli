import json
from contextlib import contextmanager

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

REPOSITORY = {"owner": "team", "repo": "project"}
TOKEN = "private-token-for-contract-tests"


@contextmanager
def catalog(response=None, *, read_only=False, allowed=()):
    requests = []

    def handler(request):
        requests.append(request)
        if callable(response):
            return response(request)
        return httpx.Response(200, json={} if response is None else response)

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        yield GitCodeTools(api, allowed_repositories=allowed, read_only=read_only), requests


def test_catalog_has_focused_schemas_and_explicit_annotations():
    with catalog() as (tools, _):
        definitions = tools.list_tools()
    assert len(definitions) == 31
    assert len({tool.name for tool in definitions}) == 31
    for tool in definitions:
        assert tool.name.startswith("gitcode_")
        assert tool.input_schema["additionalProperties"] is False
        assert {"owner", "repo"} <= set(tool.input_schema["required"])
        assert tool.annotations.read_only_hint is not None
        assert tool.annotations.destructive_hint is not None
    merge = next(tool for tool in definitions if tool.name == "gitcode_merge_pull_request")
    assert merge.annotations.destructive_hint
    assert not merge.annotations.read_only_hint
    assert {tool.name for tool in definitions if "delete" in tool.name} == {"gitcode_delete_file"}
    assert not any("raw_api" in tool.name for tool in definitions)


def test_read_only_mode_hides_and_refuses_write_calls():
    with catalog(read_only=True) as (tools, requests):
        assert len(tools.list_tools()) == 19
        assert all(tool.annotations.read_only_hint for tool in tools.list_tools())
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_create_issue", {**REPOSITORY, "title": "Should not write"})
        assert raised.value.code == "read_only"
        assert not requests


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_repository", {"owner": "team/other", "repo": "project"}),
        ("get_repository", {"owner": "team", "repo": ".."}),
        ("get_repository", {"owner": "team", "repo": "-option"}),
        ("get_repository", {"owner": "team", "repo": "project.git"}),
        ("get_repository", {**REPOSITORY, "token": "sensitive-extra-input"}),
        ("get_file_contents", {**REPOSITORY, "path": "../outside"}),
        ("get_file_contents", {**REPOSITORY, "path": "%2e%2e/outside"}),
        ("get_repository_tree", {**REPOSITORY, "sha": "main", "file_path": "../outside"}),
        ("get_repository_tree", {**REPOSITORY, "sha": "main", "per_page": 101}),
        ("list_issues", {**REPOSITORY, "per_page": 101}),
        ("get_issue", {**REPOSITORY, "issue_number": True}),
        ("get_issue", {**REPOSITORY, "issue_number": "23"}),
        ("get_branch", {**REPOSITORY, "branch": "../main"}),
        ("update_issue", {**REPOSITORY, "issue_number": 23, "state": "closed"}),
        ("update_pull_request", {**REPOSITORY, "pull_number": 23}),
        ("merge_pull_request", {**REPOSITORY, "pull_number": 23, "force": True}),
        ("approve_pull_request", {**REPOSITORY, "pull_number": 23, "event": "REQUEST_CHANGES"}),
        (
            "approve_pull_request",
            {**REPOSITORY, "pull_number": 23, "body": "unsupported-review-body"},
        ),
    ],
)
def test_invalid_arguments_fail_before_upstream_request(tool, arguments):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(f"gitcode_{tool}", arguments)
        assert raised.value.code == "invalid_arguments"
        assert "sensitive-extra-input" not in str(raised.value)
        assert not requests


def test_allowlist_is_enforced_for_reads_writes_and_fork_sources():
    with catalog(allowed=["team/project"]) as (tools, requests):
        for name, args in [
            ("get_repository", {"owner": "Team", "repo": "project"}),
            ("create_issue", {"owner": "other", "repo": "project", "title": "No"}),
            (
                "create_pull_request",
                {
                    **REPOSITORY,
                    "title": "No",
                    "head": "other:feature",
                    "base": "main",
                    "fork_path": "other/project",
                },
            ),
        ]:
            with pytest.raises(GitCodeError) as raised:
                tools.call(f"gitcode_{name}", args)
            assert raised.value.code == "repository_not_allowed"
        assert not requests


def test_unknown_tool_is_rejected():
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_raw_api", REPOSITORY)
        assert raised.value.code == "unknown_tool"
        assert not requests


def test_issue_create_and_update_keep_gitcode_endpoint_shape():
    with catalog({"number": "23"}) as (tools, requests):
        tools.call(
            "gitcode_create_issue",
            {**REPOSITORY, "title": "Example", "labels": ["bug", "regression"]},
        )
        tools.call(
            "gitcode_update_issue",
            {**REPOSITORY, "issue_number": 23, "title": "Example", "state": "close"},
        )
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v5/repos/team/issues"
    assert json.loads(requests[0].content)["labels"] == "bug,regression"
    assert json.loads(requests[0].content)["repo"] == "project"
    assert requests[1].method == "PATCH"
    assert requests[1].url.path == "/api/v5/repos/team/issues/23"
    assert json.loads(requests[1].content) == {
        "repo": "project",
        "title": "Example",
        "state": "close",
    }


@pytest.mark.parametrize(
    ("name", "extra", "suffix"),
    [
        ("list_branches", {}, "branches"),
        ("list_commits", {}, "commits"),
        ("list_issues", {}, "issues"),
        ("list_issue_comments", {"issue_number": 23}, "issues/23/comments"),
        ("list_pull_requests", {}, "pulls"),
        ("list_pull_request_comments", {"pull_number": 23}, "pulls/23/comments"),
        ("list_pull_request_commits", {"pull_number": 23}, "pulls/23/commits"),
    ],
)
def test_list_calls_are_bounded_to_one_page(name, extra, suffix):
    with catalog([{"id": 1}, {"id": 2}]) as (tools, requests):
        result = tools.call(f"gitcode_{name}", {**REPOSITORY, **extra, "page": 3, "per_page": 2})
    assert len(requests) == 1
    assert requests[0].url.path == f"/api/v5/repos/team/project/{suffix}"
    assert requests[0].url.params["page"] == "3"
    assert result["next_page"] == 4
    assert result["pagination_mode"] == "upstream"
    assert result["data"] == [{"id": 1}, {"id": 2}]


@pytest.mark.parametrize(
    ("name", "extra", "suffix"),
    [
        ("list_labels", {}, "labels"),
        ("list_milestones", {}, "milestones"),
        ("list_pull_request_files", {"pull_number": 23}, "pulls/23/files"),
    ],
)
def test_unpaged_endpoints_slice_one_bounded_response_explicitly(name, extra, suffix):
    with catalog([{"id": value} for value in range(5)]) as (tools, requests):
        result = tools.call(f"gitcode_{name}", {**REPOSITORY, **extra, "page": 2, "per_page": 2})
        last = tools.call(f"gitcode_{name}", {**REPOSITORY, **extra, "page": 3, "per_page": 2})
    assert len(requests) == 2
    assert all(request.url.path == f"/api/v5/repos/team/project/{suffix}" for request in requests)
    assert all(not request.url.params for request in requests)
    assert result["data"] == [{"id": 2}, {"id": 3}]
    assert result["next_page"] == 3
    assert result["pagination_mode"] == "client"
    assert result["total_items"] == 5
    assert "not a stable snapshot" in result["pagination_note"]
    assert last["data"] == [{"id": 4}]
    assert last["next_page"] is None


def test_clone_info_does_not_return_server_paths_or_credential_urls():
    response = {
        "default_branch": "main",
        "clone_url": f"https://user:{TOKEN}@wrong.example/repo.git",
    }
    with catalog(response) as (tools, requests):
        result = tools.call("gitcode_get_clone_info", REPOSITORY)["data"]
    assert len(requests) == 1
    assert result["https_url"] == "https://gitcode.com/team/project.git"
    assert result["ssh_url"] == "git@gitcode.com:team/project.git"
    assert result["cloned"] is False
    assert "same execution environment" in result["execution_note"]
    assert TOKEN not in json.dumps(result)


def test_branch_names_are_encoded_as_one_segment():
    with catalog() as (tools, requests):
        tools.call("gitcode_get_branch", {**REPOSITORY, "branch": "feature/test"})
    assert requests[0].url.raw_path.endswith(b"branches/feature%2Ftest")


def test_create_branch_uses_documented_gitcode_fields():
    with catalog() as (tools, requests):
        tools.call(
            "gitcode_create_branch", {**REPOSITORY, "branch_name": "feature/test", "refs": "main"}
        )
    assert json.loads(requests[0].content) == {"branch_name": "feature/test", "refs": "main"}


def test_create_pr_maps_gitcode_reviewers_testers_and_linked_issues():
    with catalog() as (tools, requests):
        tools.call(
            "gitcode_create_pull_request",
            {
                **REPOSITORY,
                "title": "Feature",
                "head": "contributor:feature",
                "base": "main",
                "fork_path": "contributor/project",
                "assignees": ["reviewer"],
                "testers": ["tester"],
                "issue_numbers": [10, 20],
                "draft": True,
            },
        )
    payload = json.loads(requests[0].content)
    assert payload["head"] == "contributor:feature"
    assert payload["fork_path"] == "contributor/project"
    assert payload["assignees"] == "reviewer"
    assert payload["testers"] == "tester"
    assert payload["inner_issue_nums"] == "10;20"
    assert "reviewers" not in payload


def test_cross_repository_pr_requires_source_path():
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError):
            tools.call(
                "gitcode_create_pull_request",
                {**REPOSITORY, "title": "Feature", "head": "other:feature", "base": "main"},
            )
        assert not requests


def test_native_review_does_not_force_or_emulate_request_changes():
    with catalog() as (tools, requests):
        tools.call("gitcode_approve_pull_request", {**REPOSITORY, "pull_number": 23})
    assert requests[0].url.path.endswith("/pulls/23/review")
    assert json.loads(requests[0].content) == {"force": False}


def test_merge_keeps_squash_separate_and_never_force_merges():
    with catalog() as (tools, requests):
        tools.call(
            "gitcode_merge_pull_request",
            {**REPOSITORY, "pull_number": 23, "merge_method": "merge", "squash": True},
        )
    assert requests[0].method == "PUT"
    assert requests[0].url.path.endswith("/pulls/23/merge")
    assert json.loads(requests[0].content) == {"merge_method": "merge", "squash": True}


def test_diff_uses_documented_files_json_and_preserves_structured_content():
    response = {
        "diff_refs": {"head_sha": "123"},
        "count": 1,
        "diffs": [{"content": {"text": [{"line_content": "change", "type": "new"}]}}],
    }
    with catalog(response) as (tools, requests):
        result = tools.call("gitcode_get_pull_request_diff", {**REPOSITORY, "pull_number": 23})
    assert requests[0].url.path.endswith("/pulls/23/files.json")
    assert requests[0].headers["Accept"] == "application/json"
    assert result["format"] == "gitcode_structured_diff"
    assert result["data"] == response


def test_tree_uses_upstream_pagination_and_preserves_metadata():
    entries = [{"path": "a"}, {"path": "b"}]
    with catalog({"tree": entries, "truncated": True, "sha": "tree-sha"}) as (tools, requests):
        result = tools.call(
            "gitcode_get_repository_tree",
            {
                **REPOSITORY,
                "sha": "feature/test",
                "recursive": True,
                "file_path": "source files",
                "page": 2,
                "per_page": 2,
            },
        )
    assert requests[0].url.raw_path.startswith(
        b"/api/v5/repos/team/project/git/trees/feature%2Ftest?"
    )
    assert dict(requests[0].url.params) == {
        "recursive": "1",
        "file_path": "source files",
        "page": "2",
        "per_page": "2",
    }
    assert result["data"] == entries
    assert result["next_page"] == 3
    assert result["pagination_mode"] == "upstream"
    assert result["upstream_metadata"] == {"truncated": True, "sha": "tree-sha"}
    assert result["upstream_truncated"] is True


def test_tree_does_not_invent_upstream_completeness_signal():
    with catalog({"tree": []}) as (tools, _):
        result = tools.call("gitcode_get_repository_tree", {**REPOSITORY, "sha": "main"})
    assert result["next_page"] is None
    assert result["upstream_truncated"] is None


def test_file_contents_preserves_encoding_and_literal_path():
    response = {"encoding": "base64", "content": "aGVsbG8=", "path": "docs/a file.txt"}
    with catalog(response) as (tools, requests):
        result = tools.call(
            "gitcode_get_file_contents",
            {**REPOSITORY, "path": "docs/a file.txt", "ref": "feature/test"},
        )
    assert requests[0].url.raw_path.startswith(
        b"/api/v5/repos/team/project/contents/docs/a%20file.txt?"
    )
    assert requests[0].url.params["ref"] == "feature/test"
    assert result["data"] == response
