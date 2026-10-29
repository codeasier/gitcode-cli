"""Offline, credential-isolated contracts for dedicated PR label endpoints."""

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.pulls import PullRequestService

ORIGIN = "https://labels.gitcode.invalid"
TOKEN = "synthetic-pr-label-contract-token"
PREFIX = "/api/v5/repos/owner/repo/pulls/42"
DOCS = Path(__file__).parents[1] / "fixtures/gitcode-api-contracts/pr-labels.json"


@pytest.fixture
def http_cli(monkeypatch):
    def reject_credentials(*args, **kwargs):
        raise AssertionError("Contracts must not read ambient credentials")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject_credentials)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject_credentials)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=ORIGIN + "/api/v5/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        try:
            yield router, CliRunner(), client
        finally:
            client.close()


def route(router, method, suffix, response=None, *, payload=None, status=200, responses=None):
    sequence = iter(responses) if responses is not None else None

    def respond(request):
        assert request.method == method
        assert request.url.host == "labels.gitcode.invalid"
        assert request.url.raw_path.split(b"?")[0] == (PREFIX + suffix).encode("ascii")
        assert dict(request.url.params) == {"access_token": TOKEN}
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers and "private-token" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert json.loads(request.content) == payload
            assert request.headers["content-type"] == "application/json"
        return httpx.Response(status, json=next(sequence) if sequence is not None else response)

    return router.request(method, ORIGIN + PREFIX + suffix).mock(side_effect=respond)


def pr(*names, **overrides):
    return {
        "number": 42,
        "id": 1042,
        "labels": [{"name": name, "id": sum(map(ord, name))} for name in names],
        **overrides,
    }


def invoke(runner, *flags):
    return runner.invoke(main, ["--token", TOKEN, "pr", "edit", "42", "-R", "owner/repo", *flags])


def test_add_uses_documented_json_array_and_preserves_existing_labels(http_cli):
    router, runner, _ = http_cli
    contract = json.loads(DOCS.read_text())["add"]
    read = route(router, "GET", "", responses=[pr("keep"), pr("keep", "help wanted", "concurrent")])
    write = route(router, contract["method"], "/labels", [], payload=contract["json"])
    result = invoke(runner, "--add-label", "help wanted")
    assert result.exit_code == 0, result.output
    assert write.call_count == 1 and read.call_count == 2
    assert [entry.request.method for entry in router.calls] == ["GET", "POST", "GET"]


@pytest.mark.parametrize("name", ["last-label", "help wanted", "a/b?#% 空", "%2F"])
def test_remove_last_label_uses_encoded_targeted_delete_without_patch(http_cli, name):
    router, runner, _ = http_cli
    contract = json.loads(DOCS.read_text())["remove"]
    route(router, "GET", "", responses=[pr(name), pr()])
    deletion = route(router, contract["method"], "/labels/" + quote(name, safe=""), {})
    result = invoke(runner, "--remove-label", name)
    assert result.exit_code == 0, result.output
    assert deletion.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "DELETE", "GET"]


def test_partial_multi_delete_does_not_retry_or_claim_success(http_cli):
    router, runner, _ = http_cli
    route(router, "GET", "", pr("first", "second"))
    first = route(router, "DELETE", "/labels/first", {})
    second = route(router, "DELETE", "/labels/second", {"message": "synthetic rejection"}, status=403)
    result = invoke(runner, "--remove-label", "first,second")
    assert result.exit_code == 1
    assert "may have been updated" in result.output and "no write was repeated" in result.output
    assert first.call_count == second.call_count == 1


def test_mixed_title_and_label_noop_cannot_return_stale_success(http_cli):
    router, runner, _ = http_cli
    read = route(router, "GET", "", responses=[pr("keep"), pr()])
    route(router, "PATCH", "", pr("keep"), payload={"title": "New title"})
    result = invoke(runner, "--title", "New title", "--add-label", "keep")
    assert result.exit_code == 1 and "labels were not confirmed" in result.output
    assert read.call_count == 2


@pytest.mark.parametrize("name", [None, [], 42, "", " ", "a,b", ".", "..", "a\nb", "a\x7fb"])
def test_service_refuses_ambiguous_delete_target_without_http(http_cli, name):
    router, _, client = http_cli
    with pytest.raises(APIError, match="unambiguous label"):
        PullRequestService(client).remove_label("owner", "repo", 42, name)
    assert not router.calls


@pytest.mark.parametrize("names", [None, "bug", [], [None], [1], [""], [" "], ["x\n"], ["x\x7f"]])
def test_service_refuses_empty_additions_without_http(http_cli, names):
    router, _, client = http_cli
    with pytest.raises(APIError, match="nonempty label"):
        PullRequestService(client).add_labels("owner", "repo", 42, names)
    assert not router.calls
