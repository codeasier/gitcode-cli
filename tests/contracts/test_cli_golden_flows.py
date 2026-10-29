"""Ordered, offline CliRunner workflows through real adapters, services and HTTPX."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import httpx
import pytest
import respx

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://flows.gitcode.invalid"
TOKEN = "synthetic-golden-flow-token"
DOCS = Path(__file__).resolve().parents[1] / "fixtures/gitcode-api-contracts/raw"
ISSUE_CREATE = ("Issues", "post-api-v-5-repos-owner-issues.json")
ISSUE_GET = ("Issues", "get-api-v-5-repos-owner-repo-issues-number.json")
ISSUE_UPDATE = ("Issues", "patch-api-v-5-repos-owner-issues-number.json")
PR_CREATE = ("Pull Requests", "post-api-v-5-repos-owner-repo-pulls.json")
PR_GET = ("Pull Requests", "get-api-v-5-repos-owner-repo-pulls-number.json")
PR_UPDATE = ("Pull Requests", "patch-api-v-5-repos-owner-repo-pulls-number.json")


@pytest.fixture
def http_cli(cli_runner, tmp_config_dir, monkeypatch):
    # Preserve AppContext.client and token resolution; replace only the client origin.
    # The shared config fixture and synthetic environment prevent ambient credential reads.
    monkeypatch.chdir(tmp_config_dir)
    monkeypatch.setenv("GC_TOKEN", TOKEN)
    monkeypatch.setenv("NO_COLOR", "1")
    # Click 8.1 (Python 3.9) needs opt-in separation; 8.2+ always captures both.
    if hasattr(cli_runner, "mix_stderr"):
        monkeypatch.setattr(cli_runner, "mix_stderr", False)
    clients = []

    def client_at_reserved_origin(*, token):
        assert token == TOKEN
        client = GitCodeClient(token=token, base_url=ORIGIN + "/api/v5/")
        clients.append(client)
        return client

    monkeypatch.setattr("gitcode_cli.context.GitCodeClient", client_at_reserved_origin)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        try:
            yield router, cli_runner
        finally:
            for client in clients:
                client.close()


def _step(fixture, response, *, payload=None, status=200):
    contract = json.loads(DOCS.joinpath(*fixture).read_text(encoding="utf-8"))
    fields = {field["name"]: field for field in contract["requestBodyFields"]}
    assert "access_token" in {field["name"] for field in contract["queryParams"]}
    if payload is not None:
        assert payload.keys() <= fields.keys()
        assert {name for name, field in fields.items() if field["required"]} <= payload.keys()
        for name, value in payload.items():
            assert type(value) is {"string": str, "integer": int, "boolean": bool}[fields[name]["type"]]
            if "enum" in fields[name]:
                assert value in fields[name]["enum"]
    path = contract["path"].format(owner="owner", repo="repo", number=42)
    return contract["method"], path, payload, status, response


def _script(router, *steps):
    """Each HTTP call must consume the next documented step, including repeated reads."""
    pending = deque(steps)

    def respond(request):
        assert pending, "Unexpected extra HTTP request (including write retry)"
        method, path, payload, status, response = pending.popleft()
        assert (request.method, request.url.path) == (method, path), "HTTP workflow order drift"
        assert request.url.scheme == "https" and request.url.host == "flows.gitcode.invalid"
        assert list(request.url.params.multi_items()) == [("access_token", TOKEN)]
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers and "private-token" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            actual = json.loads(request.content)
            assert actual == payload, "HTTP JSON body drift"
            assert all(type(actual[name]) is type(value) for name, value in payload.items())
        return httpx.Response(status, json=response)

    for method, path in {(step[0], step[1]) for step in steps}:
        router.request(method, ORIGIN + path).mock(side_effect=respond)
    return pending


def _invoke(runner, kind, operation, *args, input=None):
    # Let unexpected assertion/implementation failures escape Click's exception capture.
    result = runner.invoke(main, ["-R", "owner/repo", kind, operation, *args], input=input, catch_exceptions=False)
    assert TOKEN not in result.stdout + result.stderr
    return result


def _success(result):
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return result.stdout


def _create_args(kind, item):
    args = ["--title", item["title"], "--body", item["body"]]
    if kind == "pr":
        args += ["--base", item["base"]["ref"], "--head", item["head"]["ref"]]
    return args


def _create_payload(kind, item):
    payload = {"title": item["title"], "body": item["body"]}
    if kind == "issue":
        return {"repo": "repo", **payload}
    return {**payload, "base": item["base"]["ref"], "head": item["head"]["ref"], "draft": False}


def test_issue_create_view_close_flow(http_cli, mock_issue_data):
    router, runner = http_cli
    opened = {**mock_issue_data, "body": "Offline issue body ✓\n"}
    closed = {**opened, "state": "closed"}
    pending = _script(
        router,
        _step(ISSUE_CREATE, opened, payload=_create_payload("issue", opened), status=201),
        _step(ISSUE_GET, opened),
        _step(ISSUE_GET, opened),
        _step(ISSUE_UPDATE, closed, payload={"repo": "repo", "title": opened["title"], "state": "close"}),
        _step(ISSUE_GET, closed),
        _step(ISSUE_GET, closed),
    )

    created = _invoke(runner, "issue", "create", "--title", opened["title"], "--body-file", "-", input=opened["body"])
    assert _success(created) == opened["html_url"] + "\n"
    viewed = _invoke(runner, "issue", "view", "42", "--json", "number,title,state,body,url")
    assert json.loads(_success(viewed)) == {
        "number": 42,
        "title": opened["title"],
        "state": "OPEN",
        "body": opened["body"],
        "url": opened["html_url"],
    }
    assert "Closed issue #42" in _success(_invoke(runner, "issue", "close", "42"))
    detail = _success(_invoke(runner, "issue", "view", "42"))
    assert "#42 Test Issue" in detail and "State:\tclosed" in detail and opened["body"] in detail
    assert "already closed" in _success(_invoke(runner, "issue", "close", "42"))
    assert not pending
    assert [call.request.method for call in router.calls] == ["POST", "GET", "GET", "PATCH", "GET", "GET"]


def test_pr_create_view_edit_close_flow(http_cli, mock_pr_data, tmp_path):
    router, runner = http_cli
    opened = {**mock_pr_data, "draft": False}
    edited = {**opened, "title": "Edited PR", "body": "Body from a local UTF-8 file ✓\n"}
    closed = {**edited, "state": "closed"}
    body_file = tmp_path / "pr-body.md"
    body_file.write_text(edited["body"], encoding="utf-8")
    pending = _script(
        router,
        _step(PR_CREATE, {"number": 42}, payload=_create_payload("pr", opened), status=201),
        _step(PR_GET, opened),  # Exactly one create-output readback, not another create.
        _step(PR_GET, opened),
        _step(PR_UPDATE, edited, payload={"title": edited["title"], "body": edited["body"]}),
        _step(PR_GET, edited),
        _step(PR_UPDATE, closed, payload={"state": "closed"}),
        _step(PR_GET, closed),
    )

    created = _invoke(runner, "pr", "create", *_create_args("pr", opened), "--json", "number,state,url,draft")
    assert json.loads(_success(created)) == {"number": 42, "state": "OPEN", "url": opened["html_url"], "draft": False}
    detail = _success(_invoke(runner, "pr", "view", "42"))
    assert "#42 Test PR" in detail and "State:\topen" in detail and opened["body"] in detail
    result = _invoke(runner, "pr", "edit", "42", "--title", edited["title"], "--body-file", str(body_file))
    assert _success(result) == "Edited pull request #42\n"
    viewed = _invoke(runner, "pr", "view", "42", "--json", "number,title,state,body")
    assert json.loads(_success(viewed)) == {
        "number": 42,
        "title": edited["title"],
        "state": "OPEN",
        "body": edited["body"],
    }
    assert _success(_invoke(runner, "pr", "close", "42")) == "Closed pull request #42\n"
    viewed = _invoke(runner, "pr", "view", "42", "--json", "number,title,state")
    assert json.loads(_success(viewed)) == {"number": 42, "title": edited["title"], "state": "CLOSED"}
    assert not pending
    assert [call.request.method for call in router.calls] == ["POST", "GET", "GET", "PATCH", "GET", "PATCH", "GET"]


@pytest.mark.parametrize("kind", ["issue", "pr"])
@pytest.mark.parametrize("failure", ["forbidden", "wrong_identity"])
def test_create_output_readback_failure_is_partial_not_success(http_cli, mock_issue_data, mock_pr_data, kind, failure):
    router, runner = http_cli
    item = mock_issue_data if kind == "issue" else mock_pr_data
    create, get = (ISSUE_CREATE, ISSUE_GET) if kind == "issue" else (PR_CREATE, PR_GET)
    response = {"message": "synthetic readback denial"} if failure == "forbidden" else {**item, "number": 99}
    pending = _script(
        router,
        _step(create, {"number": 42}, payload=_create_payload(kind, item), status=201),
        _step(get, response, status=403 if failure == "forbidden" else 200),
    )

    result = _invoke(runner, kind, "create", *_create_args(kind, item), "--json", "number,title,state")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "creation returned #42, but its requested output could not be read" in result.stderr
    assert "no create request was repeated" in result.stderr
    assert not pending
    assert [call.request.method for call in router.calls] == ["POST", "GET"]


@pytest.mark.parametrize("kind", ["issue", "pr"])
def test_close_write_error_does_not_report_success_or_retry(http_cli, mock_issue_data, kind):
    router, runner = http_cli
    steps = []
    if kind == "issue":
        steps.append(_step(ISSUE_GET, mock_issue_data))
        update, payload = ISSUE_UPDATE, {"repo": "repo", "title": mock_issue_data["title"], "state": "close"}
    else:
        update, payload = PR_UPDATE, {"state": "closed"}
    steps.append(_step(update, {"message": "synthetic close rejection"}, payload=payload, status=422))
    pending = _script(router, *steps)

    result = _invoke(runner, kind, "close", "42")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "synthetic close rejection" in result.stderr
    assert "Closed" not in result.stderr
    assert not pending
    assert [call.request.method for call in router.calls] == (["GET", "PATCH"] if kind == "issue" else ["PATCH"])


def test_pr_close_unconfirmed_state_is_not_success(http_cli, mock_pr_data):
    router, runner = http_cli
    pending = _script(router, _step(PR_UPDATE, mock_pr_data, payload={"state": "closed"}))

    result = _invoke(runner, "pr", "close", "42")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "PR close was not confirmed" in result.stderr
    assert "Verify the remote state before retrying" in result.stderr
    assert not pending
    assert len(router.calls) == 1


def test_unregistered_cli_request_fails_instead_of_mock_success(http_cli):
    _, runner = http_cli
    with pytest.raises(AssertionError, match="not mocked"):
        _invoke(runner, "issue", "view", "42")
