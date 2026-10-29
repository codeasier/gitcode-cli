"""Offline CLI synchronization preflight; never calls a real repository."""

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://sync.gitcode.invalid"
TOKEN = "synthetic-sync-contract-token"
PATH = "/api/v5/repos/owner/repo"


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
            yield router, CliRunner()
        finally:
            client.close()


def route(router, method, suffix, payload, status=200):
    def respond(request):
        assert request.method == method and request.url.path == PATH + suffix
        assert request.url.host == "sync.gitcode.invalid"
        assert dict(request.url.params) == {"access_token": TOKEN}
        assert request.headers["private-token"] == TOKEN
        assert request.headers["accept"] == "application/json"
        assert "authorization" not in request.headers and not request.content
        return httpx.Response(status, json=payload)

    return router.request(method, ORIGIN + PATH + suffix).mock(side_effect=respond)


def invoke(runner):
    return runner.invoke(main, ["--token", TOKEN, "repo", "sync", "owner/repo"])


@pytest.mark.parametrize("fork", [False, 0])
def test_non_fork_does_not_reach_sync_endpoint(http_cli, fork):
    router, runner = http_cli
    route(router, "GET", "", {"fork": fork})
    result = invoke(runner)
    assert result.exit_code == 1 and "owner/repo is not a fork" in result.output
    assert "no synchronization request was sent" in result.output
    assert len(router.calls) == 1


@pytest.mark.parametrize("payload", [{}, [], {"fork": None}, {"fork": "false"}, {"fork": 2}, {"fork": 1.0}])
def test_unknown_forkness_never_becomes_a_write(http_cli, payload):
    router, runner = http_cli
    route(router, "GET", "", payload)
    result = invoke(runner)
    assert result.exit_code == 1 and "Cannot verify whether" in result.output
    assert len(router.calls) == 1


@pytest.mark.parametrize("fork", [True, 1])
def test_known_fork_preserves_one_sync_request(http_cli, fork):
    router, runner = http_cli
    route(router, "GET", "", {"fork": fork})
    write = route(router, "PUT", "/sync_repo", {"repo_sync_result": True})
    result = invoke(runner)
    assert result.exit_code == 0, result.output
    assert "Synced" in result.output and write.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "PUT"]


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_failed_preflight_never_reaches_write(http_cli, status):
    router, runner = http_cli
    route(router, "GET", "", {"message": "synthetic unavailable"}, status)
    result = invoke(runner)
    assert result.exit_code == 1 and "Synced" not in result.output
    assert len(router.calls) == 1
