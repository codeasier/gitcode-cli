"""Repository-search behavior at the CLI and dedicated v5 HTTP boundaries."""

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
def invoke():
    # Click 8.1 merges stderr into stdout unless explicitly disabled.
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))
    return lambda *args: runner.invoke(main, ["--token", TOKEN, "search", "repos", "example", *args])


@pytest.fixture
def search(monkeypatch, invoke):
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(TOKEN, base_url=BASE)
        monkeypatch.setattr(AppContext, "client", lambda _: client)
        try:
            yield router.get(BASE + "search/repositories"), invoke
        finally:
            client.close()


@pytest.mark.parametrize(
    "args",
    [
        ["--include-forks", "true"],
        ["--include-forks", "only"],
        ["--sort", "watches", "--order", "asc"],
        ["--sort", "watches", "--order", "desc"],
        ["--include-forks", "true", "--sort", "watches"],
        ["--include-forks", "false", "--sort", "watches"],
    ],
)
def test_unavailable_search_modes_fail_before_client(monkeypatch, invoke, args):
    monkeypatch.setattr(AppContext, "client", lambda _: pytest.fail("unexpected search client"))
    result = invoke(*args, "-L", "100", "--json", "fullName,watchersCount")
    assert result.exit_code == 2 and "Invalid value" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("explicit", [False, True])
def test_repository_options_on_every_wire_page(search, explicit):
    route, invoke = search

    def row(i):
        # Omission must not add validation or silently re-sort by watch count.
        return {"id": i, "watchers_count": i % 3, **({"fork": False if i % 2 else 0} if explicit else {})}

    route.mock(
        side_effect=[
            httpx.Response(200, json=[row(i) for i in range(20)]),
            httpx.Response(200, json=[row(20), row(21)]),
        ]
    )
    options = ["--include-forks", "false"] if explicit else []
    result = invoke(*options, "--sort", "stars", "--order", "desc", "-L", "21", "--json", "id,watchersCount")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"id": i, "watchersCount": i % 3} for i in range(21)]
    assert route.call_count == 2
    for page, (request, _) in enumerate(route.calls, 1):
        assert dict(request.url.params) == {
            "q": "example",
            "per_page": "20",
            "page": str(page),
            "sort": "stars_count",
            "order": "desc",
            "access_token": TOKEN,
            **({"fork": "false"} if explicit else {}),
        }
        assert not request.content
        assert "authorization" not in request.headers and "private-token" not in request.headers


@pytest.mark.parametrize(
    "metadata", [{"fork": True}, {"fork": 1}, {}, {"fork": None}, {"fork": "false"}, {"fork": 0.0}]
)
def test_explicit_exclusion_does_not_trust_a_200_or_emit_partial_rows(search, metadata):
    route, invoke = search
    # A violation on the second page must not leak the first page or trigger a third request.
    route.mock(
        side_effect=[
            httpx.Response(200, json=[{"id": i, "fork": False} for i in range(20)]),
            httpx.Response(200, json=[{"id": i, "fork": False} for i in range(20, 39)] + [{"id": 39, **metadata}]),
        ]
    )
    result = invoke("--include-forks", "false", "-L", "100", "--json", "id")
    assert result.exit_code == 1 and "non-fork" in result.stderr
    assert not result.stdout and route.call_count == 2


@pytest.mark.parametrize("status", [403, 422])
def test_rejected_option_does_not_retry_with_broader_search(search, status):
    route, invoke = search
    route.respond(status, json={"message": "repository search option denied"})
    result = invoke("--include-forks", "false", "--json", "id")
    assert result.exit_code == 1 and "repository search option denied" in result.stderr
    assert not result.stdout
    assert TOKEN not in result.stdout and TOKEN not in result.stderr
    assert route.call_count == 1
