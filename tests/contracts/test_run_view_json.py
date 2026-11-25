"""Wire-level run view JSON contracts; the provider and credential are synthetic."""

from __future__ import annotations

import json
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.actions_client import ActionsClient
from gitcode_cli.cli import main
from gitcode_cli.commands import actions

SHA = "ab" * 20
RUN = {"workflow_run_id": "r-42", "attempt": 0, "head_sha": SHA, "workflow_name": "构建 🚲"}
TOKEN = "fixture-auth-value"


@pytest.fixture
def call(monkeypatch):
    requests = []
    reply = {"json": RUN}
    opts = {"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}

    def handle(request):
        requests.append(request)
        assert request.method == "GET"
        assert (request.url.scheme, request.url.host) == ("https", "api.gitcode.com")
        assert request.url.path == "/api/v8/repos/org/repo/actions/runs/r-42"
        assert list(request.url.params.multi_items()) == [("access_token", TOKEN)]
        assert not request.content
        return httpx.Response(200, **reply)

    monkeypatch.setattr(
        actions, "ActionsClient", lambda token: ActionsClient(token, transport=httpx.MockTransport(handle))
    )

    def invoke(*args):
        return CliRunner(**opts).invoke(main, ["--token", TOKEN, "-R", "org/repo", "run", "view", "r-42", *args])

    return invoke, requests, reply


@pytest.mark.parametrize("sha", [SHA, "cd" * 32])
def test_run_metadata_one_snapshot_selected_exact_keys_in_requested_order(call, sha):
    invoke, requests, reply = call
    reply["json"] = {**RUN, "head_sha": sha, "stages": [{"jobs": [{"inputs": "not-public"}]}], "title": "different"}
    result = invoke(
        "-R", "gitcode.com/org/repo", "-a", "0", "--commit", sha.upper(), "--json", "workflowName, attempt,headSha"
    )
    assert result.exit_code == 0 and result.stderr == ""
    assert json.loads(result.stdout, object_pairs_hook=list) == [
        ("workflowName", "构建 🚲"),
        ("attempt", 0),
        ("headSha", sha),
    ]
    assert len(requests) == 1


def test_run_single_field_no_unselected_workflow_name_dependency(call):
    invoke, requests, reply = call
    reply["json"] = {key: value for key, value in RUN.items() if key != "workflow_name"}
    result = invoke("--json", "headSha")
    assert result.exit_code == 0 and json.loads(result.stdout) == {"headSha": SHA}
    assert len(requests) == 1


@pytest.mark.parametrize(
    "args",
    [
        ("--json", ""),
        ("--json", "headSha,"),
        ("--json", "attempt,attempt"),
        ("--json", "jobs"),
        ("--json", "conclusion"),
        ("--json", "headSha", "--json", "attempt"),
        ("--job", "j"),
        ("--job", ""),
        ("--with-steps",),
        ("--log",),
        ("--step", "s"),
        ("--limit", "20"),
        ("--offset", "0"),
        ("--sort", "asc"),
        ("--commit", "ab"),
        ("-R", "github.com/org/repo"),
        ("-R", "another/repo"),
    ],
)
def test_incompatible_options_fail_before_request(call, args):
    invoke, requests, _ = call
    result = invoke(*args) if "--json" in args else invoke("--json", "attempt", *args)
    assert result.exit_code != 0 and result.stdout == "" and result.stderr and not requests


@pytest.mark.parametrize(
    ("changes", "args"),
    [
        ({"workflow_run_id": "r-99"}, ()),
        ({"attempt": None}, ()),
        ({"attempt": True}, ()),
        ({"attempt": -1}, ()),
        ({"attempt": "0"}, ()),
        ({"head_sha": "abc"}, ()),
        ({"head_sha": None}, ()),
        ({}, ("--attempt", "1")),
        ({}, ("--commit", "1" * 40)),
    ],
)
def test_required_identity_checked_even_if_not_selected(call, changes, args):
    invoke, requests, reply = call
    reply["json"] = {**RUN, **changes}
    result = invoke("--json", "workflowName", *args)
    assert result.exit_code == 1 and result.stdout == "" and result.stderr and len(requests) == 1


@pytest.mark.parametrize("name", [None, True, 12, {}, [], "", "  ", TOKEN, "access_token=private-fixture"])
def test_bad_selected_name_no_fabricated_or_redacted_value(call, name):
    invoke, requests, reply = call
    reply["json"] = {**RUN, "workflow_name": name}
    result = invoke("--json", "attempt,workflowName")
    assert result.exit_code == 1 and result.stdout == "" and result.stderr and len(requests) == 1
    assert TOKEN not in result.stderr and "private-fixture" not in result.stderr


def test_help_does_not_fetch(call):
    invoke, requests, _ = call
    result = invoke("--help")
    assert result.exit_code == 0 and "JSON FIELDS" in result.stdout and not requests
    for field in ("attempt", "headSha", "workflowName"):
        assert field in result.stdout
