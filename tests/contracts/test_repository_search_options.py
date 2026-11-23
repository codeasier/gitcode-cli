"""Offline wire contracts for the dedicated v5 repository search endpoint."""

import json
from inspect import signature

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext

BASE = "https://repo-search.invalid/api/v5/"
TOKEN = "synthetic-search-token"


@pytest.fixture
def search(monkeypatch):
    # Supply a synthetic token explicitly; never resolve an ambient credential.
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=BASE)
        monkeypatch.setattr(AppContext, "client", lambda _: client)
        try:
            # Click 8.1 merges stderr into stdout unless explicitly disabled.
            runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))
            yield (
                router.get(BASE + "search/repositories"),
                lambda *args: runner.invoke(main, ["--token", TOKEN, "search", "repos", "example", *args]),
            )
        finally:
            client.close()


@pytest.mark.parametrize("fork", [None, "false", "true"])
def test_repository_options_on_every_wire_page(search, fork):
    route, invoke = search

    # A successful inclusion request can return both forks and original repositories.
    def row(i):
        return {"id": i, "full_name": f"repo/{i}", "fork": fork == "true" and i % 2 == 0, "watchers_count": i}

    route.mock(
        side_effect=[
            httpx.Response(200, json=[row(i) for i in range(20)]),
            httpx.Response(200, json=[row(20), row(21)]),
        ]
    )
    options = [] if fork is None else ["--include-forks", fork]
    result = invoke(*options, "--sort", "watches", "--order", "asc", "-L", "21", "--json", "fullName,watchersCount")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"fullName": f"repo/{i}", "watchersCount": i} for i in range(21)]
    assert route.call_count == 2
    for page, (request, _) in enumerate(route.calls, 1):
        assert dict(request.url.params) == {
            "q": "example",
            "per_page": "20",
            "page": str(page),
            "sort": "watches_count",
            "order": "asc",
            "access_token": TOKEN,
            **({"fork": fork} if fork is not None else {}),
        }
        assert not request.content
        assert "authorization" not in request.headers and "private-token" not in request.headers


@pytest.mark.parametrize("status", [403, 422])
def test_rejected_option_does_not_retry_with_broader_search(search, status):
    route, invoke = search
    route.respond(status, json={"message": "repository search option denied"})
    result = invoke("--include-forks", "true", "--sort", "watches", "--json", "id")
    assert result.exit_code == 1 and "repository search option denied" in result.stderr
    assert not result.stdout
    assert TOKEN not in result.stdout and TOKEN not in result.stderr
    assert route.call_count == 1
