"""Strict, credential-isolated CLI → service → HTTP milestone-setting contracts."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://milestones.gitcode.invalid"
TOKEN = "synthetic-milestone-contract-token"
PREFIX = "/api/v5/repos/owner/repo"
DOCS = Path(__file__).resolve().parents[1] / "fixtures/gitcode-api-contracts/raw/Pull Requests"


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


def _route(router, method, suffix, response, *, payload=None, query=None, status=200, raw=None):
    def respond(request):
        assert request.method == method
        assert request.url.scheme == "https" and request.url.host == "milestones.gitcode.invalid"
        assert request.url.path == PREFIX + suffix
        assert dict(request.url.params) == {"access_token": TOKEN, **(query or {})}
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers
        assert "private-token" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
            assert "milestone" not in payload
            assert type(payload["milestone_number"]) is int
        return httpx.Response(status, text=raw) if raw is not None else httpx.Response(status, json=response)

    return router.request(method, ORIGIN + PREFIX + suffix).mock(side_effect=respond)


def _invoke(runner, operation, value, *options):
    args = ["--token", TOKEN, "pr", operation]
    if operation == "create":
        args += ["--title", "Title", "--body", "Body", "--base", "main", "--head", "feature"]
    else:
        args += ["42"]
    return runner.invoke(main, [*args, "-R", "owner/repo", "--milestone", value, *options])


def _payload(operation):
    payload = {"milestone_number": 7}
    if operation == "create":
        payload.update(title="Title", body="Body", base="main", head="feature", draft=False)
    return payload


@pytest.mark.parametrize("operation", ["create", "edit"])
@pytest.mark.parametrize("title", [False, True])
def test_documented_number_field_and_confirmed_readback(http_cli, operation, title):
    router, runner = http_cli
    filename = (
        "post-api-v-5-repos-owner-repo-pulls.json"
        if operation == "create"
        else "patch-api-v-5-repos-owner-repo-pulls-number.json"
    )
    contract = json.loads(DOCS.joinpath(filename).read_text(encoding="utf-8"))
    fields = {field["name"]: field for field in contract["requestBodyFields"]}
    assert fields["milestone_number"]["type"] == "integer"
    assert "milestone" not in fields
    if title:
        _route(
            router,
            "GET",
            "/milestones",
            [{"number": 7, "title": "v1"}],
            query={"state": "all", "page": "1", "per_page": "100"},
        )
    suffix = "/pulls" if operation == "create" else "/pulls/42"
    method = "POST" if operation == "create" else "PATCH"
    assert contract["path"].format(owner="owner", repo="repo", number=42) == PREFIX + suffix
    write = _route(router, method, suffix, {"number": "42"}, payload=_payload(operation))
    read = _route(
        router,
        "GET",
        "/pulls/42",
        {"number": 42, "milestone": {"number": 7}, "html_url": "https://gitcode.com/owner/repo/pulls/42"},
    )

    result = _invoke(runner, operation, "v1" if title else "007")

    assert result.exit_code == 0, result.output
    assert write.call_count == read.call_count == 1
    assert [entry.request.method for entry in router.calls] == (["GET"] if title else []) + [method, "GET"]


@pytest.mark.parametrize("title", [False, True])
def test_dry_run_resolves_title_but_never_writes(http_cli, title):
    router, runner = http_cli
    if title:
        _route(
            router,
            "GET",
            "/milestones",
            [{"number": 7, "title": "v1"}],
            query={"state": "all", "page": "1", "per_page": "100"},
        )

    result = _invoke(runner, "create", "v1" if title else "7", "--dry-run")

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == _payload("create")
    assert [entry.request.method for entry in router.calls] == (["GET"] if title else [])


@pytest.mark.parametrize("operation", ["create", "edit"])
@pytest.mark.parametrize(
    "status,body",
    [(200, {}), (200, {"milestone": {"number": 8}}), (403, {"message": "Synthetic rejection"})],
)
def test_readback_failure_exposes_partial_success_without_second_write(http_cli, operation, status, body):
    router, runner = http_cli
    method = "POST" if operation == "create" else "PATCH"
    suffix = "/pulls" if operation == "create" else "/pulls/42"
    write = _route(router, method, suffix, {"number": 42}, payload=_payload(operation))
    read = _route(router, "GET", "/pulls/42", body, status=status)

    result = _invoke(runner, operation, "7")

    assert result.exit_code == 1
    assert "PR #42 may have been created or updated" in result.output
    assert "no write was repeated" in result.output
    assert "Created pull request" not in result.output and "Edited pull request" not in result.output
    assert write.call_count == read.call_count == 1
    assert [entry.request.method for entry in router.calls] == [method, "GET"]


@pytest.mark.parametrize("items", [[], [{"number": 7, "title": "v1"}, {"number": 8, "title": "v1"}]])
def test_missing_or_ambiguous_title_performs_no_write(http_cli, items):
    router, runner = http_cli
    _route(router, "GET", "/milestones", items, query={"state": "all", "page": "1", "per_page": "100"})

    result = _invoke(runner, "create", "v1")

    assert result.exit_code == 1
    assert "no PR write was attempted" in result.output
    assert [entry.request.method for entry in router.calls] == ["GET"]


def test_create_without_number_never_reposts(http_cli):
    router, runner = http_cli
    write = _route(router, "POST", "/pulls", {}, payload=_payload("create"))

    result = _invoke(runner, "create", "7")

    assert result.exit_code == 1
    assert "creation may have succeeded" in result.output
    assert write.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["POST"]


@pytest.mark.parametrize("operation", ["create", "edit"])
@pytest.mark.parametrize("raw", ["<html>Synthetic error</html>", '{"milestone":'])
def test_non_json_readback_preserves_partial_success_message(http_cli, operation, raw):
    router, runner = http_cli
    method = "POST" if operation == "create" else "PATCH"
    suffix = "/pulls" if operation == "create" else "/pulls/42"
    write = _route(router, method, suffix, {"number": 42}, payload=_payload(operation))
    read = _route(router, "GET", "/pulls/42", None, raw=raw)

    result = _invoke(runner, operation, "7")

    assert result.exit_code == 1
    assert "PR #42 may have been created or updated" in result.output
    assert "no write was repeated" in result.output
    assert raw not in result.output
    assert "Created pull request" not in result.output and "Edited pull request" not in result.output
    assert write.call_count == read.call_count == 1
    assert [entry.request.method for entry in router.calls] == [method, "GET"]
