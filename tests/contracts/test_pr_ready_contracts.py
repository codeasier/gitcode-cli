"""Strict offline HTTP contract for ready/undo, including the no-write path."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://contract.gitcode.invalid"
TOKEN = "synthetic-ready-contract-token"
PATH = "/api/v5/repos/owner/repo/pulls/42"
DOCS = Path(__file__).resolve().parents[1] / "fixtures/gitcode-api-contracts/raw/Pull Requests"


@pytest.fixture(autouse=True)
def reject_ambient_credentials(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("Contracts must not read ambient credentials or configuration")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject)


def _assert_request(request, method):
    assert request.method == method
    assert request.url.scheme == "https" and request.url.host == "contract.gitcode.invalid"
    assert request.url.path == PATH
    assert request.url.params.multi_items() == [("access_token", TOKEN)]
    assert request.headers["accept"] == "application/json"
    assert "private-token" not in request.headers
    assert "authorization" not in request.headers


@pytest.mark.parametrize("undo", [False, True])
@pytest.mark.parametrize("already", [False, True])
def test_ready_uses_boolean_draft_and_skips_redundant_patch(monkeypatch, undo, already):
    get_contract = json.loads(
        DOCS.joinpath("get-api-v-5-repos-owner-repo-pulls-number.json").read_text(encoding="utf-8")
    )
    update_contract = json.loads(
        DOCS.joinpath("patch-api-v-5-repos-owner-repo-pulls-number.json").read_text(encoding="utf-8")
    )
    response_fields = {field["name"]: field for field in get_contract["responseFields"]}
    request_fields = {field["name"]: field for field in update_contract["requestBodyFields"]}
    assert response_fields["draft"]["type"] == "boolean"
    assert request_fields["draft"]["type"] == "boolean"
    expected_path = update_contract["path"].format(owner="owner", repo="repo", number=42)
    assert expected_path == PATH
    reads = iter([undo] if already else [not undo, undo])

    def read(request):
        _assert_request(request, "GET")
        assert not request.content
        return httpx.Response(200, json={"number": 42, "draft": next(reads)})

    def update(request):
        _assert_request(request, "PATCH")
        assert request.headers["content-type"] == "application/json"
        payload = json.loads(request.content)
        assert payload == {"draft": undo}
        assert type(payload["draft"]) is bool
        return httpx.Response(200, json={"number": 42})

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        get_route = router.get(ORIGIN + PATH).mock(side_effect=read)
        patch_route = None if already else router.patch(ORIGIN + PATH).mock(side_effect=update)
        client = GitCodeClient(TOKEN, base_url=f"{ORIGIN}/api/v5/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        args = ["--token", TOKEN, "pr", "ready", "42", "-R", "owner/repo"]
        if undo:
            args.append("--undo")
        try:
            result = CliRunner().invoke(main, args, env={"GC_TOKEN": TOKEN})
        finally:
            client.close()

        assert result.exit_code == 0, result.output
        assert get_route.call_count == (1 if already else 2)
        if patch_route is not None:
            assert patch_route.call_count == 1
        else:
            assert "already" in result.output


@pytest.mark.parametrize("raw", ["<html>Synthetic error</html>", '{"draft":'])
@pytest.mark.parametrize("undo", [False, True])
def test_invalid_json_readback_reports_uncertainty_without_repeating_patch(monkeypatch, raw, undo):
    reads = iter([httpx.Response(200, json={"draft": not undo}), httpx.Response(200, text=raw)])

    def read(request):
        _assert_request(request, "GET")
        assert not request.content
        return next(reads)

    def update(request):
        _assert_request(request, "PATCH")
        assert json.loads(request.content) == {"draft": undo}
        return httpx.Response(200, json={"number": 42})

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        get_route = router.get(ORIGIN + PATH).mock(side_effect=read)
        patch_route = router.patch(ORIGIN + PATH).mock(side_effect=update)
        client = GitCodeClient(TOKEN, base_url=f"{ORIGIN}/api/v5/")
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        args = ["--token", TOKEN, "pr", "ready", "42", "-R", "owner/repo"]
        if undo:
            args.append("--undo")
        try:
            result = CliRunner().invoke(main, args)
        finally:
            client.close()

        assert result.exit_code == 1
        assert "update may have succeeded" in result.output
        assert "before retrying" in result.output
        assert "Marked" not in result.output and "Converted" not in result.output and raw not in result.output
        assert get_route.call_count == 2 and patch_route.call_count == 1
