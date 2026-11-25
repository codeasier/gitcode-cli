"""Native Kanban list, v5 contract 244. Strict in-process transport; no account or network."""

from __future__ import annotations

import json
import logging
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import rest_api
from gitcode_cli.cli import main
from gitcode_cli.errors import APIError
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command
from gitcode_cli.services.dashboards import dashboard_page

TOKEN = "synthetic-dashboard-token"
TRACE = "trace-never-print"


def board(**extra):
    return {
        "id": "board-a1",
        "iid": 8,
        "name": "研发协作",
        "description": "not selected",
        "status": 0,
        "visibility": 1,
        "updated_at": "2026-02-06",
        "internal": {"trace": TRACE},
        **extra,
    }


def envelope(*rows):
    return {"open_count": 3, "close_count": 0, "all_count": 3, "content": list(rows), "trace": TRACE}


@pytest.fixture
def command(monkeypatch, tmp_config_dir):
    requests = []

    def invoke(args, response=None, *, token="", root=(), separate_stderr=False):
        def handler(request):
            assert not requests, "Unexpected second request"
            requests.append(request)
            assert response is not None, "Unexpected network attempt"
            if isinstance(response, Exception):
                raise response
            return response

        requests.clear()
        monkeypatch.setattr(rest_api, "open_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        opts = {"mix_stderr": False} if separate_stderr and "mix_stderr" in signature(CliRunner).parameters else {}
        return CliRunner(**opts).invoke(main, [*root, "org", "dashboards", *args], env={"GC_TOKEN": token})

    return invoke, requests


def test_single_anonymous_page(command):
    invoke, requests = command
    result = invoke(["--org", "acme"], httpx.Response(200, json=envelope(board())))
    assert result.exit_code == 0 and result.output == "8\t研发协作\n"
    (request,) = requests
    assert request.method == "GET" and not request.content
    assert (request.url.scheme, request.url.host, request.url.path) == (
        "https",
        "api.gitcode.com",
        "/api/v5/org/acme/kanban/list",
    )
    assert dict(request.url.params) == {"page": "1", "per_page": "20", "visibility": "1"}
    assert "authorization" not in request.headers and "private-token" not in request.headers


def test_explicit_pat_reads_private_board_with_exact_projection(command, caplog):
    invoke, requests = command
    caplog.set_level(logging.DEBUG)
    result = invoke(
        ["--org", "release-eng", "--page", "2", "--per-page", "1", "--json", "name,id,visibility,status,iid"],
        httpx.Response(200, json=envelope(board(name="Board " + TOKEN, visibility=2, status=1, iid=0))),
        root=("--token", TOKEN),
    )
    assert result.exit_code == 0 and json.loads(result.output) == [
        {"name": "Board [REDACTED]", "id": "board-a1", "visibility": 2, "status": 1, "iid": 0}
    ]
    (request,) = requests
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert "private-token" not in request.headers
    assert str(request.url) == "https://api.gitcode.com/api/v5/org/release-eng/kanban/list?page=2&per_page=1"
    assert TOKEN not in result.output + caplog.text
    assert TRACE not in result.output + caplog.text


def test_empty_page_and_terminal_safe_names(command):
    invoke, _ = command
    empty = invoke(["--org", "acme", "--json", "iid"], httpx.Response(200, json=envelope()))
    assert empty.exit_code == 0 and json.loads(empty.output) == []
    unsafe = "board\x1b[2J\n\u202e"
    result = invoke(["--org", "acme"], httpx.Response(200, json=envelope(board(name=unsafe))))
    assert result.exit_code == 0 and result.output == f"8\t{json.dumps(unsafe)}\n"


@pytest.mark.parametrize("status", [200, 201, 202, 204, 206, 302, 400, 401, 403, 404, 429, 500])
def test_provider_errors_do_not_echo_body_or_redirect(command, status):
    invoke, requests = command
    response = httpx.Response(
        status, headers={"Location": "https://example.invalid/" + TRACE}, content=(TRACE + TOKEN).encode()
    )
    result = invoke(["--org", "acme"], response, token=TOKEN)
    assert result.exit_code == 1 and len(requests) == 1
    assert TRACE not in result.output and TOKEN not in result.output
    assert "Traceback" not in result.output


def test_unexpected_success_status_is_not_a_page(command):
    invoke, _ = command
    result = invoke(["--org", "acme"], httpx.Response(206, json=envelope(board())))
    assert result.exit_code == 1 and "206" in result.output and "研发协作" not in result.output


def test_network_error_no_retry_or_trace(command):
    invoke, requests = command
    result = invoke(["--org", "acme"], httpx.ReadTimeout(TRACE), token=TOKEN)
    assert result.exit_code == 1 and len(requests) == 1 and TRACE not in result.output


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"content": []},
        {**envelope(), "open_count": False},
        {**envelope(), "all_count": -1},
        {**envelope(), "content": {}},
        envelope(board(), board(id="board-b"), board(id="board-c")),
        envelope(board(), None),
        envelope(board(), board(id="")),
        envelope(board(), board(id="board-b", name={})),
        envelope(board(), board(id="board-b", iid=True)),
        envelope(board(), board(id="board-b", status=False)),
        envelope(board(), board(id="board-b", visibility={"access_token": TRACE})),
        envelope(board(), board()),
    ],
)
def test_invalid_page_never_returns_partial_rows(command, body):
    invoke, requests = command
    result = invoke(["--org", "acme", "--per-page", "2", "--json", "id"], httpx.Response(200, json=body))
    assert result.exit_code == 1 and len(requests) == 1
    assert "board-a1" not in result.output and TRACE not in result.output


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--org", "acme", "--json", "extra"],
        ["--org", "first", "--org", "second"],
        ["--org", "acme", "--json", "name,description"],
        ["--org", "acme", "--per-page", "101"],
        ["--org", "acme", "--page", "0"],
        ["--org", "acme", "--page", "10001"],
        *(["--org", name] for name in ("https://example.invalid/x", "..", "a/b", "%2f", "a?b", "a\nb", "a" * 256)),
    ],
)
def test_invalid_inputs_fail_before_transport(command, args):
    invoke, requests = command
    assert invoke(args).exit_code != 0 and not requests


def test_repo_flag_and_active_token_are_never_mistaken_for_org(command):
    invoke, requests = command
    assert invoke(["--org", "acme"], root=("-R", "elsewhere/repo")).exit_code == 2 and not requests
    result = invoke(["--org", TOKEN], token=TOKEN)
    assert result.exit_code == 1 and TOKEN not in result.output and not requests


def test_service_pagination_bounds():
    with pytest.raises(APIError, match="pagination"):
        dashboard_page("acme", True, 2, token="")


@pytest.mark.parametrize("visibility", [0, 2, 3, None, "1", True])
def test_anonymous_private_or_unknown_row_leaks_no_output(command, visibility):
    invoke, requests = command
    result = invoke(
        ["--org", "acme", "--json", "name"],
        httpx.Response(
            200, json=envelope(board(name="public-first"), board(id="board-b", name=TRACE, visibility=visibility))
        ),
    )
    assert result.exit_code == 1 and len(requests) == 1
    assert requests[0].url.params["visibility"] == "1"
    assert TRACE not in result.output and "public-first" not in result.output


@pytest.mark.parametrize("token", ["", TOKEN])
@pytest.mark.parametrize("fields", [{"status": 9}, {"visibility": 0}, {"status": -1}, {"status": 0.0}])
def test_unknown_enum_in_either_mode_fails_whole_page(command, token, fields):
    invoke, _ = command
    result = invoke(
        ["--org", "acme"],
        httpx.Response(200, json=envelope(board(name="public-first"), board(id="board-b", name=TRACE, **fields))),
        token=token,
    )
    assert result.exit_code == 1 and "public-first" not in result.output and TRACE not in result.output


@pytest.mark.parametrize("field", ["id", "name"])
def test_unpaired_surrogate_is_malformed_even_for_an_unselected_field(command, field):
    invoke, requests = command
    unsafe = board(id="board-b")
    unsafe[field] += chr(0xD800)
    raw = json.dumps(envelope(board(name="public-first"), unsafe)).encode()
    result = invoke(["--org", "acme", "--json", "iid"], httpx.Response(200, content=raw))
    assert result.exit_code == 1 and len(requests) == 1
    assert "Malformed dashboard identity or name" in result.output and "iid" not in result.output


@pytest.mark.parametrize("token", ["", TOKEN])
def test_duplicate_visibility_never_uses_last_wins(command, token):
    invoke, requests = command
    raw = json.dumps(envelope(board(name=TRACE))).replace('"visibility": 1', '"visibility": 2, "visibility": 1')
    result = invoke(
        ["--org", "acme", "--json", "iid"],
        httpx.Response(200, content=raw),
        token=token,
        separate_stderr=True,
    )
    assert result.exit_code == 1 and len(requests) == 1 and not result.stdout
    assert "valid JSON" in result.stderr and TRACE not in result.stderr


def test_direct_only_command_discovery(command):
    invoke, requests = command
    result = invoke(["--help"])
    assert result.exit_code == 0 and "JSON FIELDS" in result.output and "not GitHub Projects" in result.output
    assert not requests
    for argv in (["project", "list"], ["org", "dashboards", "--org", "acme"]):
        with pytest.raises(ProxyError, match="refusing to fall back"):
            validate_gitcode_command(argv)
