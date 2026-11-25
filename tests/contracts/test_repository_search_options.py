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
from gitcode_cli.errors import APIError

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
            httpx.Response(200, headers={"set-cookie": "session=synthetic; Path=/"}, json=[row(i) for i in range(20)]),
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
            **({"fork": "false"} if explicit else {}),
        }
        assert not request.content
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert "private-token" not in request.headers and "cookie" not in request.headers


@pytest.mark.parametrize("token", [TOKEN, ""])
@pytest.mark.parametrize("status", [401, 403, 302])
def test_repo_search_denial_never_retries_or_emits_partial_rows(token, status, monkeypatch, tmp_config_dir):
    monkeypatch.setenv("GC_TOKEN", token)
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[{"id": n, "full_name": f"owner/r{n}"} for n in range(20)])
        return httpx.Response(status, headers={"location": "https://other.invalid/"}, json={"message": "denied"})

    client = GitCodeClient(token, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(AppContext, "client", lambda _: client)
    try:
        result = CliRunner().invoke(main, ["search", "repos", "msinsight", "-L", "21", "--json", "fullName"])
    finally:
        client.close()
    assert result.exit_code == 1 and "denied" in result.output
    assert "owner/r" not in result.output and TOKEN not in result.output
    assert len(requests) == 2
    for page, request in enumerate(requests, 1):
        assert request.url.host == "api.gitcode.com" and request.url.path == "/api/v5/search/repositories"
        assert dict(request.url.params) == {"q": "msinsight", "page": str(page), "per_page": "20"}
        assert request.headers.get("authorization") == (f"Bearer {token}" if token else None)
        assert "private-token" not in request.headers and "cookie" not in request.headers


@pytest.mark.parametrize("field", ["q", "language", "Authorization", "access_token", "private-token"])
def test_repo_search_never_sends_credential_query(field):
    def unexpected(_request):
        pytest.fail("request sent with credential fields")

    client = GitCodeClient(TOKEN, transport=httpx.MockTransport(unexpected))
    try:
        with pytest.raises(APIError) as error:
            client.get("/search/repositories", params={field: TOKEN if field in ("language", "q") else "other"})
        assert TOKEN not in str(error.value)
    finally:
        client.close()


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
