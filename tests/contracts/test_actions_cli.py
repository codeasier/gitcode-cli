"""No sockets: verify paths, provenance, read/write semantics and single submission using a mock transport."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.actions_client import MAX_RESPONSE, ActionsClient
from gitcode_cli.commands import actions
from gitcode_cli.context import AppContext
from gitcode_cli.errors import APIError, NetworkError
from gitcode_cli.services.actions import MAX_LOG, ActionsService

SHA, OTHER = "a" * 40, "b" * 40
RUN = {
    "workflow_run_id": "111",
    "workflow_id": "1",
    "workflow_name": "build",
    "run_number": 2,
    "event": "MR",
    "head_sha": SHA,
    "status": "COMPLETED",
}
DETAIL = {**RUN, "attempt": 2, "stages": [{"inputs": "must-not-surface"}]}
JOB = {
    "id": "job-a",
    "exec_id": "execution-a",
    "name": "compile",
    "status": "FAILED",
    "steps": [
        {
            "id": "step-a",
            "job_run_id": "execution-a",
            "name": "compile",
            "status": "FAILED",
            "inputs": "must-not-surface",
        }
    ],
}
GATE = {"ci_state_passed": True, "merge_request_switch": {"only_allow_merge_if_pipeline_succeeds": True}}
PR = {"number": 42, "head": {"sha": SHA}, "can_merge_check": False, "mergeable_state": GATE}
BASE = "/api/v8/repos/o/r/actions/"
SYNTHETIC = "fixture-only-token"


@pytest.fixture
def api(monkeypatch):
    expected = []
    calls = []
    v5 = MagicMock()

    def handler(req):
        assert req.url.host == "api.gitcode.com"
        assert "private-token" not in req.headers
        assert req.url.params.get("access_token") == SYNTHETIC
        assert "cookie" not in req.headers
        if req.url.path == "/api/v5/repos/o/r/pulls/42":
            assert req.method == "GET" and set(req.url.params) == {"access_token"} and not req.content
            response = v5.get()
            return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
        method, suffix, result, query, body, http = expected.pop(0)
        calls.append((method, suffix))
        assert (req.method, req.url.path) == (method, BASE + suffix)
        assert {k: v for k, v in req.url.params.items() if k != "access_token"} == query
        assert (json.loads(req.content) if req.content else None) == body
        if isinstance(result, Exception):
            raise result
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(http, json=result)

    def expect(suffix, result, *, method="GET", query=None, body=None, http=200):
        expected.append((method, suffix, result, query or {}, body, http))

    def factory(token):
        return ActionsClient(token, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(actions, "ActionsClient", factory)
    app = AppContext(token=SYNTHETIC, repo="gitcode.com/o/r")

    def invoke(command, *args, token=SYNTHETIC):
        test_app = app if token == SYNTHETIC else AppContext(token=token, repo=app.repo)
        result = CliRunner().invoke(command, args, obj={"app": test_app})
        if result.exception and not isinstance(result.exception, (SystemExit, APIError, NetworkError)):
            raise result.exception
        return result

    yield expect, invoke, v5, calls
    assert expected == []


def q(*, page="1", limit="20", **kwargs):
    return {"page": page, "per_page": limit, **kwargs}


def page(rows, total=None):
    return {"total_count": len(rows) if total is None else total, "workflow_runs": rows}


def test_list(api):
    expect, invoke, _, _ = api
    expect(
        "runs",
        page([RUN], 2),
        query=q(limit="1", workflow_id="1", branch="main", status="FAILED", event="MR", pull_request_id="42"),
    )
    result = invoke(actions.run, "list", "-L1", "-bmain", "-w1", "--pr", "42", "-eMR", "-sFAILED")
    assert result.exit_code == 0
    assert json.loads(result.output)["next_page"] == 2


def test_view_run_jobs_and_step_window(api):
    expect, invoke, _, _ = api
    for suffix, data in (("jobs", {"total_count": 2, "jobs": [JOB, {**JOB, "id": "job-b"}]}), ("jobs/job-a", JOB)):
        expect("runs/111", DETAIL)
        expect(f"runs/111/{suffix}", data)
        expect("runs/111", DETAIL)
    jobs = invoke(actions.run, "view", "111", "-a2", "--commit", SHA, "--limit", "1")
    assert json.loads(jobs.output)["next_offset"] == 1
    assert json.loads(jobs.output)["jobs"] == [{"id": "job-a", "name": "compile", "status": "FAILED"}]
    result = invoke(actions.run, "view", "111", "--job", "job-a")
    assert result.exit_code == 0 and "must-not-surface" not in result.output
    assert json.loads(result.output)["steps"][0]["job_run_id"] == "execution-a"


@pytest.mark.parametrize(
    ("order", "offset", "start", "end", "next_offset"), [("asc", 0, 0, 3, 3), ("desc", 10, 5, 10, 5)]
)
def test_step_log(api, order, offset, start, end, next_offset):
    expect, invoke, _, _ = api
    expect("runs/111", DETAIL)
    expect("runs/111/jobs/job-a", JOB)
    expect(
        "runs/111/jobs/job-a/logs",
        {"log": "\x1b[31m error: " + SYNTHETIC, "start_offset": start, "end_offset": end, "has_more": True},
        method="POST",
        body={"step_id": "step-a", "offset": offset, "limit": 7, "sort": order},
    )
    expect("runs/111", DETAIL)
    ret = invoke(
        actions.run,
        "view",
        "111",
        "--job",
        "job-a",
        "--log",
        "--step",
        "step-a",
        "--limit",
        "7",
        "--offset",
        str(offset),
        "--sort",
        order,
    )
    assert ret.exit_code == 0 and SYNTHETIC not in ret.output and "\x1b" not in ret.output
    assert json.loads(ret.output)["next_offset"] == next_offset


def test_attempt_race_discards_logs(api):
    expect, invoke, _, _ = api
    expect("runs/111", DETAIL)
    expect("runs/111/jobs/job-a", JOB)
    expect(
        "runs/111/jobs/job-a/logs",
        {"log": "incorrect-run-log", "start_offset": 0, "end_offset": 1, "has_more": False},
        method="POST",
        body={"step_id": "step-a", "offset": 0, "limit": 20, "sort": "asc"},
    )
    expect("runs/111", {**DETAIL, "attempt": 3})
    ret = invoke(actions.run, "view", "111", "-jjob-a", "--log", "--step", "step-a")
    assert isinstance(ret.exception, APIError) and "incorrect-run-log" not in ret.output


@pytest.mark.parametrize(
    "args",
    [
        ("view", "111", "--log"),
        ("view", "111", "--step", "x"),
        ("view", "111", "--sort", "desc"),
        ("list", "--limit", "101"),
        ("rerun", "111"),
    ],
)
def test_invalid_usage_without_http(api, args):
    _, invoke, _, calls = api
    assert invoke(actions.run, *args).exit_code == 2 and not calls


def test_workflows(api):
    expect, invoke, _, _ = api
    expect("workflows", {"total_count": 0, "workflows": []}, query=q(page="2"))
    assert json.loads(invoke(actions.workflow, "list", "--page", "2").output)["workflows"] == []
    expect(
        "workflows/ci.yml/dispatches",
        {"workflow_run_id": "111", "workflow_id": "1"},
        method="POST",
        http=201,
        body={"inputs": {"value": "a=b"}, "ref": "features/two"},
    )
    ret = invoke(actions.workflow, "run", "ci.yml", "--ref", "features/two", "-f", "value=a=b")
    assert json.loads(ret.output)["workflow_run_id"] == "111"
    assert invoke(actions.workflow, "run", "ci.yml", "-r", "main", "-f", "k=a", "-f", "k=b").exit_code == 2


@pytest.mark.parametrize(
    ("extra", "suffix", "body"),
    [([], "rerun", None), (["--job-run-id", "execution-a"], "retry", {"job_run_ids": ["execution-a"]})],
)
def test_rerun_scope(api, extra, suffix, body):
    expect, invoke, _, _ = api
    expect("runs/111", DETAIL)
    if extra:
        expect("runs/111/jobs", {"total_count": 1, "jobs": [JOB]})
        expect("runs/111", DETAIL)
    expect(f"runs/111/{suffix}", {"success": True}, method="POST", body=body)
    res = invoke(actions.run, "rerun", "111", "--commit", SHA, "--attempt", "2", *extra)
    assert json.loads(res.output)["scope"] == (["execution-a"] if extra else "entire_run")


def test_retry_unknown_execution_id_no_write(api):
    expect, invoke, _, calls = api
    expect("runs/111", DETAIL)
    expect("runs/111/jobs", {"total_count": 1, "jobs": [JOB]})
    res = invoke(actions.run, "rerun", "111", "--commit", SHA, "--attempt", "2", "--job-run-id", "job-a")
    assert isinstance(res.exception, APIError) and all(v[0] == "GET" for v in calls)


def checkq(size="25", page="1"):
    return q(page=page, limit=size, event="MR", pull_request_id="42")


@pytest.mark.parametrize(
    ("run_status", "exit_code", "outcome"),
    [
        ("COMPLETED", 0, "observed_completed"),
        ("RUNNING", 8, "pending"),
        ("FAILED", 1, "failed_or_canceled"),
        ("IGNORED", 3, "unknown_status"),
    ],
)
def test_checks_gates_and_observed_attempt_are_independent(api, run_status, exit_code, outcome):
    expect, invoke, v5, _ = api
    v5.get.return_value = PR
    old = {**RUN, "workflow_run_id": "444", "run_number": 1, "head_sha": OTHER}
    expect("runs", page([RUN, old]), query=checkq())
    expect("runs/111", {**DETAIL, "status": run_status})
    if run_status == "COMPLETED":
        expect("runs", page([RUN, old]), query=checkq())
        expect("runs/111", DETAIL)
    ret = invoke(actions.pr_checks, "42")
    assert ret.exit_code == exit_code
    report = json.loads(ret.output)
    assert report["reported_gates"]["can_merge_check"] is False and report["outcome"] == outcome
    assert report["observed_actions"]["runs"][0]["run"]["attempt"] == 2
    assert v5.get.call_count == 2


@pytest.mark.parametrize(
    ("rows", "total", "outcome"),
    [
        ([{**RUN, "head_sha": OTHER}], 1, "unknown_revision"),
        ([], 0, "no_observed_runs"),
        ([{**RUN, "head_sha": OTHER}], 2, "incomplete_scan"),
        ([{**RUN, "workflow_run_id": ""}], 1, "unknown"),
        ([{**RUN, "event": "Push"}], 1, "unknown"),
    ],
)
def test_checks_unknown_is_not_success(api, rows, total, outcome):
    expect, invoke, v5, _ = api
    v5.get.return_value = PR
    expect("runs", page(rows, total), query=checkq("1"))
    ret = invoke(actions.pr_checks, "42", "--scan-limit", "1")
    assert ret.exit_code == 3 and json.loads(ret.output)["outcome"] == outcome


def test_checks_next_page_latest_and_head_change(api):
    expect, invoke, v5, _ = api
    v5.get.side_effect = [PR, {**PR, "head": {"sha": OTHER}}]
    rows = [{**RUN, "run_number": n, "workflow_run_id": str(n)} for n in range(25)]
    expect("runs", page(rows, 26), query=checkq())
    expect("runs", page([{**RUN, "run_number": 25}], 26), query=checkq(page="2"))
    expect("runs/111", {**DETAIL, "run_number": 25})
    expect("runs", page(rows, 26), query=checkq())
    expect("runs", page([{**RUN, "run_number": 25}], 26), query=checkq(page="2"))
    expect("runs/111", {**DETAIL, "run_number": 25})
    result = invoke(actions.pr_checks, "42")
    assert result.exit_code == 3
    assert json.loads(result.output)["outcome"] == "head_changed"
    assert json.loads(result.output)["observed_actions"]["observed_for_sha"] == SHA


def test_checks_unavailable(api):
    expect, invoke, v5, _ = api
    v5.get.return_value = PR
    expect("runs", {}, http=403, query=checkq())
    report = json.loads(invoke(actions.pr_checks, "42").output)
    assert report["outcome"] == "actions_unavailable" and report["reported_gates"]["ci_state_passed"]


def test_checks_no_head(api):
    _, invoke, v5, _ = api
    v5.get.return_value = {**PR, "head": {"sha": "abc"}}
    assert json.loads(invoke(actions.pr_checks, "42").output)["outcome"] == "unknown_head"


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (httpx.ConnectError("sensitive text"), NetworkError),
        (httpx.Response(200, text="not json"), APIError),
        (httpx.Response(200, json=[]), APIError),
        (httpx.Response(200, content=b"a" * (MAX_RESPONSE + 1)), APIError),
        (httpx.Response(302, headers={"Location": "https://never.invalid/"}), APIError),
    ],
)
def test_bound_and_no_follow_or_secret_echo(api, exc, kind):
    expect, invoke, _, calls = api
    expect("runs", exc, query=q())
    result = invoke(actions.run, "list")
    assert isinstance(result.exception, kind) and len(calls) == 1
    assert SYNTHETIC not in str(result.exception) and "sensitive text" not in str(result.exception)


@pytest.mark.parametrize("http", [202, 403, 502])
def test_no_automatic_write_retry(api, http):
    expect, invoke, _, calls = api
    expect("workflows/ci.yml/dispatches", {}, method="POST", http=http, body={"ref": "main", "inputs": {}})
    result = invoke(actions.workflow, "run", "ci.yml", "-r", "main")
    assert "Verify remote runs" in str(result.exception) and len(calls) == 1


@pytest.mark.parametrize("value", [".", "..", "../other", "a%2fb", "/a", "https://example.com", "a#b", ""])
def test_bad_path_no_request(api, value):
    _, invoke, _, calls = api
    assert isinstance(invoke(actions.run, "view", value).exception, APIError) and not calls


def test_log_shape_size_and_cursor_contract():
    svc = ActionsService(MagicMock(), "o", "r")
    for bad in [{"log": 4}, {"log": "x" * (MAX_LOG + 1)}, {"has_more": True}, {"end_offset": -1}]:
        svc.client.call.return_value = {"log": "", "start_offset": 0, "end_offset": 0, "has_more": False, **bad}
        with pytest.raises(APIError):
            svc.logs("111", JOB, "step-a", 0, 1, "asc")
    with pytest.raises(APIError, match="not present"):
        svc.logs("111", JOB, "other", 0, 1, "asc")


@pytest.mark.parametrize(
    ("listed", "latest", "detail_expected"),
    [
        ([RUN], {**DETAIL, "attempt": 3, "status": "RUNNING"}, True),
        ([{**RUN, "workflow_run_id": "other", "run_number": 3}], DETAIL, False),
    ],
)
def test_checks_same_head_cannot_green_after_run_or_attempt_changes(api, listed, latest, detail_expected):
    expect, invoke, v5, _ = api
    v5.get.return_value = PR
    expect("runs", page([RUN]), query=checkq())
    expect("runs/111", DETAIL)
    expect("runs", page(listed), query=checkq())
    if detail_expected:
        expect("runs/111", latest)
    result = invoke(actions.pr_checks, "42")
    assert result.exit_code == 3
    report = json.loads(result.output)
    assert report["outcome"] == "actions_changed"
    assert report["observed_actions"]["outcome"] == "observed_completed"
    assert v5.get.call_count == 2


@pytest.mark.parametrize(
    ("gate", "exit_code", "outcome"),
    [
        ({**GATE, "ci_state_passed": False}, 1, "ci_gate_not_passed"),
        ({"ci_state_passed": True}, 3, "ci_gate_unverified"),
        (
            {"ci_state_passed": True, "merge_request_switch": {"only_allow_merge_if_pipeline_succeeds": False}},
            3,
            "ci_gate_unverified",
        ),
    ],
)
def test_completed_runs_do_not_override_unpassed_or_disabled_gate(api, gate, exit_code, outcome):
    expect, invoke, v5, _ = api
    # A same-head configuration/gate change between snapshots is enough to prevent exit 0.
    v5.get.side_effect = [PR, {**PR, "mergeable_state": gate}]
    for _ in range(2):
        expect("runs", page([RUN]), query=checkq())
        expect("runs/111", DETAIL)
    result = invoke(actions.pr_checks, "42")
    assert result.exit_code == exit_code
    report = json.loads(result.output)
    assert report["outcome"] == outcome
    assert report["observed_actions"]["stable_on_reread"]


def test_v5_snapshot_error_keeps_response_body_and_location_out_of_diagnostics(api):
    _, invoke, v5, calls = api
    v5.get.return_value = httpx.Response(
        403, json={"message": "private-body"}, headers={"Location": "https://untrusted.invalid/"}
    )
    result = invoke(actions.pr_checks, "42")
    assert isinstance(result.exception, APIError) and result.exception.status_code == 403
    assert "private-body" not in str(result.exception) and "untrusted.invalid" not in str(result.exception)
    assert "private-body" not in result.output and not calls


@pytest.mark.parametrize("scope", [[], ["--job-run-id", "execution-a"]])
def test_write_requires_auth_before_any_request(api, scope):
    _, invoke, _, calls = api
    result = invoke(actions.run, "rerun", "111", "--commit", SHA, "--attempt", "2", *scope, token="")
    assert "Authenticate with gc" in str(result.exception)
    result = invoke(actions.workflow, "run", "ci.yml", "--ref", "main", token="")
    assert "Authenticate with gc" in str(result.exception) and not calls


@pytest.mark.parametrize(
    "job_payload",
    [
        {"total_count": 2, "jobs": [JOB]},
        {"total_count": 1, "jobs": [{**JOB, "exec_id": "other"}]},
        {"total_count": 1, "jobs": [{**JOB, "steps": []}]},
        {"total_count": 1, "jobs": [{**JOB, "steps": [{"job_run_id": "other"}]}]},
        {"total_count": 2, "jobs": [JOB, {**JOB, "id": "other-job", "status": "COMPLETED"}]},
    ],
)
def test_retry_unverified_execution_identity_never_writes(api, job_payload):
    expect, invoke, _, calls = api
    expect("runs/111", DETAIL)
    expect("runs/111/jobs", job_payload)
    res = invoke(actions.run, "rerun", "111", "--commit", SHA, "--attempt", "2", "--job-run-id", "execution-a")
    assert isinstance(res.exception, APIError) and len(calls) == 2 and all(v[0] == "GET" for v in calls)


def test_retry_discards_job_identity_if_attempt_changed(api):
    expect, invoke, _, calls = api
    expect("runs/111", DETAIL)
    expect("runs/111/jobs", {"total_count": 1, "jobs": [JOB]})
    expect("runs/111", {**DETAIL, "attempt": 3})
    res = invoke(actions.run, "rerun", "111", "--commit", SHA, "--attempt", "2", "--job-run-id", "execution-a")
    assert "requested commit/attempt" in str(res.exception) and all(v[0] == "GET" for v in calls)


def test_dispatch_exact_identity_mismatch_is_uncertain_without_retry(api):
    expect, invoke, _, calls = api
    expect(
        "workflows/1/dispatches",
        {"workflow_run_id": "111", "workflow_id": "2"},
        method="POST",
        http=201,
        body={"ref": "main", "inputs": {}},
    )
    result = invoke(actions.workflow, "run", "1", "--ref", "main")
    assert "Unconfirmed workflow dispatch" in str(result.exception)
    assert "Verify remote runs" in str(result.exception) and len(calls) == 1


def test_dispatch_active_token_is_never_sent_as_workflow_input(api):
    _, invoke, _, calls = api
    result = invoke(actions.workflow, "run", "ci.yml", "--ref", "main", "-f", f"value={SYNTHETIC}")
    assert "Refusing to include" in str(result.exception) and SYNTHETIC not in str(result.exception) and not calls


def test_transport_ignores_environment_and_clears_cookies(monkeypatch, api):
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8888")
    client = ActionsClient(SYNTHETIC)
    try:
        assert not client._http.trust_env and not client._http.follow_redirects
    finally:
        client.close()
    expect, invoke, v5, _ = api
    v5.get.return_value = httpx.Response(200, json=PR, headers={"Set-Cookie": "session=test; Path=/"})
    expect("runs", page([]), query=checkq())
    assert invoke(actions.pr_checks, "42").exit_code == 3
