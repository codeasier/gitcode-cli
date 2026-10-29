"""Offline fork command/adapter → service → real CLI HTTP serialization contracts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.adapters.repos import RepoAdapter
from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError
from gitcode_cli.services.repos import RepoService

ORIGIN = "https://contract.gitcode.invalid"
TOKEN = "synthetic-fork-contract-token"
CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures/gitcode-api-contracts/raw/Repositories/post-api-v-5-repos-owner-repo-forks.json"
)


@pytest.fixture
def strict_http():
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        yield router


@pytest.fixture
def client(strict_http):
    transport = GitCodeClient(token=TOKEN, base_url=f"{ORIGIN}/api/v5/")
    try:
        yield transport
    finally:
        transport.close()


def _fork_route(router, organization, response, *, status=200):
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    path = contract["path"].format(owner="owner", repo="repo")
    fields = {field["name"]: field for field in contract["requestBodyFields"]}

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == contract["method"]
        assert request.url.scheme == "https" and request.url.host == "contract.gitcode.invalid"
        assert request.url.path == path
        assert request.url.params.multi_items() == [("access_token", TOKEN)]
        assert request.headers["accept"] == "application/json"
        # Preserve the CLI repository-only header; this is not MCP bearer authentication.
        assert request.headers["private-token"] == TOKEN
        assert "authorization" not in request.headers
        if organization is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            payload = json.loads(request.content)
            assert set(payload) <= fields.keys()
            assert payload == {"organization": organization}
            assert type(payload["organization"]) is str
        return httpx.Response(status, json=response)

    return router.request(contract["method"], ORIGIN + path).mock(side_effect=respond)


@pytest.mark.parametrize("organization", [None, "my-org"])
def test_fork_command_serializes_documented_destination(client, strict_http, monkeypatch, organization):
    namespace = organization or "personal"
    item = {"full_name": f"{namespace}/repo", "namespace": {"full_path": namespace}}
    route = _fork_route(strict_http, organization, item)
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    args = ["repo", "fork", "owner/repo"]
    if organization is not None:
        args += ["--org", organization]

    result = CliRunner().invoke(main, args, env={"GC_TOKEN": TOKEN})

    assert result.exit_code == 0, result.output
    assert f"Created fork {namespace}/repo" in result.output
    assert route.call_count == 1


@pytest.mark.parametrize("response", [{}, {"full_name": "personal/repo"}])
def test_success_http_status_cannot_confirm_wrong_org_or_trigger_clone(client, strict_http, monkeypatch, response):
    route = _fork_route(strict_http, "my-org", response)
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    clone = MagicMock()
    monkeypatch.setattr("gitcode_cli.commands.repo._git_clone", clone)

    result = CliRunner().invoke(
        main, ["repo", "fork", "owner/repo", "--org", "my-org", "--clone"], env={"GC_TOKEN": TOKEN}
    )

    assert result.exit_code == 1
    assert "Created fork" not in result.output
    assert "verify your GitCode repositories before retrying" in result.output
    assert route.call_count == 1
    clone.assert_not_called()


def test_unavailable_org_is_not_retried_in_personal_namespace(client, strict_http):
    route = _fork_route(strict_http, "my-org", {"message": "Organization is unavailable"}, status=403)

    with pytest.raises(APIError, match="Organization is unavailable"):
        RepoAdapter(RepoService(client)).fork_repo("owner", "repo", org="my-org")

    assert route.call_count == 1
