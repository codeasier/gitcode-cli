"""Credential-isolated real-client contracts for consistent structured output."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://projection.gitcode.invalid"
TOKEN = "synthetic-projection-contract-token"
PREFIX = "/api/v5/repos/owner/repo"
COMMON = "number,state,url,createdAt,updatedAt"


@pytest.fixture
def http_cli(monkeypatch):
    def reject_credentials(*args, **kwargs):
        raise AssertionError("Contracts must not read ambient credentials or configuration")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject_credentials)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=f"{ORIGIN}/api/v5/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        try:
            yield router, CliRunner()
        finally:
            client.close()


def _route(router, method, path, response, *, payload=None, status=200, raw=None, private_token=False):
    def respond(request):
        assert request.method == method
        assert request.url.scheme == "https" and request.url.host == "projection.gitcode.invalid"
        assert request.url.path == path
        assert request.url.params["access_token"] == TOKEN
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers
        if private_token:
            assert request.headers["private-token"] == TOKEN
        else:
            assert "private-token" not in request.headers
        if method == "POST":
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
            assert request.url.params.multi_items() == [("access_token", TOKEN)]
        else:
            assert not request.content
        return httpx.Response(status, text=raw) if raw is not None else httpx.Response(status, json=response)

    return router.request(method, ORIGIN + path).mock(side_effect=respond)


def _invoke(runner, kind, operation, fields=COMMON, *options):
    args = ["--token", TOKEN, kind, operation, "-R", "owner/repo"]
    if operation == "create":
        args += ["--title", "Title", "--body", "Body"]
        if kind == "pr":
            args += ["--head", "feature", "--base", "main"]
    elif operation == "view":
        args.append("42")
    return runner.invoke(main, [*args, "--json", fields, *options])


def _create_payload(kind):
    payload = {"title": "Title", "body": "Body"}
    if kind == "pr":
        payload.update(head="feature", base="main", draft=False)
    else:
        payload["repo"] = "repo"
    return payload


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("operation", ["create", "list", "view"])
def test_same_common_projection_across_create_list_and_view(http_cli, kind, operation):
    router, runner = http_cli
    resource = "issues" if kind == "issue" else "pulls"
    item = {
        "number": "42",
        "state": "opened",
        "html_url": f"https://gitcode.com/owner/repo/{resource}/42",
        "url": f"https://gitcode.com/api/v5/repos/owner/repo/{resource}/42",
        "created_at": "2026-10-29T00:00:00Z",
        "updated_at": "2026-10-29T01:00:00Z",
    }
    if operation == "create":
        path = PREFIX + "/pulls" if kind == "pr" else "/api/v5/repos/owner/issues"
        route = _route(router, "POST", path, item, payload=_create_payload(kind))
    else:
        path = PREFIX + f"/{resource}" + ("/42" if operation == "view" else "")
        route = _route(router, "GET", path, [item] if operation == "list" else item)

    result = _invoke(runner, kind, operation)

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    if operation == "list":
        assert len(output) == 1
        output = output[0]
    assert output == {
        "number": 42,
        "state": "OPEN",
        "url": item["html_url"],
        "createdAt": item["created_at"],
        "updatedAt": item["updated_at"],
    }
    assert route.call_count == 1 and len(router.calls) == 1


def test_pr_create_raw_ref_draft_fields_are_projected_without_get(http_cli):
    router, runner = http_cli
    _route(
        router,
        "POST",
        PREFIX + "/pulls",
        {"number": 42, "source_branch": "feature", "target_branch": "main", "work_in_progress": 0},
        payload=_create_payload("pr"),
    )

    result = _invoke(runner, "pr", "create", "head,base,draft,headRefName,baseRefName")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "head": {"ref": "feature"},
        "base": {"ref": "main"},
        "draft": False,
        "headRefName": "feature",
        "baseRefName": "main",
    }
    assert len(router.calls) == 1


def test_issue_create_missing_requested_milestone_uses_one_readback(http_cli):
    router, runner = http_cli
    payload = {**_create_payload("issue"), "milestone": 7}
    _route(router, "POST", "/api/v5/repos/owner/issues", {"number": "42"}, payload=payload)
    _route(router, "GET", PREFIX + "/issues/42", {"number": "42", "milestone": {"number": 7, "title": "v1"}})

    result = _invoke(runner, "issue", "create", "milestone", "--milestone", "7")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"milestone": {"number": 7, "title": "v1"}}
    assert [entry.request.method for entry in router.calls] == ["POST", "GET"]


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("raw", ["<html>Synthetic failure</html>", '{"number":'])
def test_create_invalid_json_readback_reports_created_number_without_retry(http_cli, kind, raw):
    router, runner = http_cli
    resource = "issues" if kind == "issue" else "pulls"
    post_path = PREFIX + "/pulls" if kind == "pr" else "/api/v5/repos/owner/issues"
    _route(router, "POST", post_path, {"number": "42"}, payload=_create_payload(kind))
    _route(router, "GET", PREFIX + f"/{resource}/42", None, raw=raw)

    result = _invoke(runner, kind, "create", "createdAt")

    assert result.exit_code == 1
    assert "creation returned #42" in result.output
    assert "no create request was repeated" in result.output
    assert raw not in result.output
    assert [entry.request.method for entry in router.calls] == ["POST", "GET"]


def test_pr_milestone_confirmed_readback_is_reused_for_json(http_cli):
    router, runner = http_cli
    _route(
        router,
        "POST",
        PREFIX + "/pulls",
        {"number": 42},
        payload={**_create_payload("pr"), "milestone_number": 7},
    )
    _route(router, "GET", PREFIX + "/pulls/42", {"number": 42, "milestone": {"number": 7}})

    result = _invoke(runner, "pr", "create", "createdAt,milestone", "--milestone", "7")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"createdAt": None, "milestone": {"number": 7}}
    assert [entry.request.method for entry in router.calls] == ["POST", "GET"]


def test_org_repository_output_uses_paths_without_modifying_display_names(http_cli):
    router, runner = http_cli
    _route(
        router,
        "GET",
        "/api/v5/users/my-org/repos",
        {"message": "Synthetic user not found"},
        status=404,
        private_token=True,
    )
    _route(
        router,
        "GET",
        "/api/v5/orgs/my-org/repos",
        [
            {
                "full_name": "My Org / Repo Display",
                "namespace": {"full_path": "my-org"},
                "path": "repo",
                "name": "Repo Display",
            }
        ],
        private_token=True,
    )

    result = runner.invoke(
        main, ["--token", TOKEN, "repo", "list", "my-org", "-L", "1", "--json", "name,nameWithOwner"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"name": "Repo Display", "nameWithOwner": "my-org/repo"}]
    assert [entry.request.method for entry in router.calls] == ["GET", "GET"]


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("status,body", [(403, {"message": "Synthetic rejection"}), (200, {"number": 43}), (200, None)])
def test_failed_or_wrong_object_readback_never_repeats_creation(http_cli, kind, status, body):
    router, runner = http_cli
    resource = "issues" if kind == "issue" else "pulls"
    post_path = PREFIX + "/pulls" if kind == "pr" else "/api/v5/repos/owner/issues"
    _route(router, "POST", post_path, {"number": 42}, payload=_create_payload(kind))
    _route(router, "GET", PREFIX + f"/{resource}/42", body, status=status)

    result = _invoke(runner, kind, "create", "createdAt")

    assert result.exit_code == 1
    assert "creation returned #42" in result.output
    assert "no create request was repeated" in result.output
    assert [entry.request.method for entry in router.calls] == ["POST", "GET"]


def test_pr_dry_run_keeps_request_payload_and_makes_no_requests(http_cli):
    router, runner = http_cli

    result = _invoke(runner, "pr", "create", "head,base,draft", "--dry-run")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == _create_payload("pr")
    assert len(router.calls) == 0
