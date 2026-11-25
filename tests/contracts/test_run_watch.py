"""Production Click path, bounded clocks, no sockets: watch may only GET the pinned run detail."""

from __future__ import annotations

import json
from queue import Queue
from threading import Event, Thread, current_thread

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import actions_watch
from gitcode_cli.actions_client import ActionsClient
from gitcode_cli.cli import main
from gitcode_cli.commands import actions
from gitcode_cli.errors import NetworkError

ROW = {"workflow_run_id": "r7", "head_sha": "a" * 40, "attempt": 0, "status": "COMPLETED"}
SYNTHETIC = "offline-watch-token"


@pytest.fixture
def watch(monkeypatch):
    calls = []

    def invoke(rows, *options, run_args=("r7",)):
        expected = iter(rows)

        def route(request):
            calls.append((request.method, request.url.path))
            assert request.url.scheme == "https" and request.url.host == "api.gitcode.com"
            assert calls[-1] == ("GET", "/api/v8/repos/o/r/actions/runs/r7")
            assert not request.content and dict(request.url.params) == {"access_token": SYNTHETIC}
            row = next(expected)  # Any extra read (including after terminal/error) fails.
            if callable(row):
                row = row()
            if isinstance(row, Exception):
                raise row
            return row if isinstance(row, httpx.Response) else httpx.Response(200, json=row)

        monkeypatch.setattr(
            actions, "ActionsClient", lambda token: ActionsClient(token, transport=httpx.MockTransport(route))
        )
        argv = ["--token", SYNTHETIC, "-R", "o/r", "run", "watch", *run_args, *options]
        return CliRunner().invoke(main, argv)

    return invoke, calls


@pytest.fixture
def fast_poll(monkeypatch):
    pauses = []

    class FastStop(Event):
        def wait(self, timeout=None):
            pauses.append(timeout)
            return self.is_set()

    monkeypatch.setattr(actions_watch, "Event", FastStop)
    return pauses


@pytest.mark.parametrize(
    ("terminal", "options", "exit_code"),
    [
        ("COMPLETED", (), 0),
        ("COMPLETED", ("--exit-status",), 0),
        ("FAILED", (), 0),
        ("FAILED", ("--exit-status",), 1),
        ("CANCELED", (), 0),
        ("CANCELED", ("--exit-status",), 1),
        ("IGNORED", (), 3),
        ("IGNORED", ("--exit-status",), 3),
    ],
)
def test_terminal_is_observation_not_pr_gate(watch, fast_poll, terminal, options, exit_code):
    invoke, calls = watch
    row = {**ROW, "status": terminal}
    ret = invoke([{**row, "stages": [{"inputs": SYNTHETIC}]}], *options)
    assert ret.exit_code == exit_code, ret.output
    assert json.loads(ret.output) == row
    assert len(calls) == 1 and not fast_poll


def test_only_transitions_and_terminal(watch, fast_poll):
    invoke, calls = watch
    states = ["RUNNING", "PAUSED", "SUSPEND", "RUNNING", "RUNNING", "COMPLETED"]
    ret = invoke([{**ROW, "status": status} for status in states], "-i", "7", "--exit-status")
    assert ret.exit_code == 0, ret.output
    assert ret.output.count("Run status: RUNNING") == 2
    assert "Run status: PAUSED" in ret.output and "Run status: SUSPEND" in ret.output
    assert json.loads(ret.output[ret.output.index("{") :]) == ROW
    assert len(calls) == len(states) and fast_poll == [7] * (len(states) - 1)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("workflow_run_id", "other"),
        ("workflow_run_id", None),
        ("head_sha", "b" * 40),
        ("head_sha", "x"),
        ("head_sha", None),
        ("attempt", 1),
        ("attempt", False),
        ("attempt", None),
        ("attempt", -1),
        ("status", "SUCCESS"),
        ("status", "completed"),
        ("status", ""),
        ("status", None),
        ("status", []),
        ("status", True),
        ("status", "inject\n" + SYNTHETIC),
    ],
)
def test_changed_or_missing_identity_or_unknown_status_is_not_terminal(watch, fast_poll, key, value):
    invoke, calls = watch
    bad = dict(ROW)
    if value is None:
        bad.pop(key)
    else:
        bad[key] = value
    ret = invoke([{**ROW, "status": "RUNNING"}, bad])
    assert ret.exit_code == 1 and "error:" in ret.output and "{" not in ret.output
    assert len(calls) == 2 and SYNTHETIC not in ret.output and "inject" not in ret.output


@pytest.mark.parametrize(
    "bad",
    [
        httpx.ConnectError(SYNTHETIC),
        httpx.Response(403, text=SYNTHETIC),
        httpx.Response(302, headers={"location": "https://foreign.invalid/"}),
        httpx.Response(200, text="not JSON"),
    ],
)
def test_http_error_or_redirect_is_not_retried(watch, fast_poll, bad):
    invoke, calls = watch
    ret = invoke([bad])
    assert ret.exit_code == 1 and "error:" in ret.output
    assert len(calls) == 1 and not fast_poll and SYNTHETIC not in ret.output


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("../r7",),
        ("r7", "--compact"),
        ("r7", "-i0"),
        ("r7", "-i61"),
        ("r7", "--timeout", "0"),
        ("r7", "--timeout", "901"),
        ("r7", "-R", "github.com/o/r"),
    ],
)
def test_explicit_id_bounds_and_host_before_io(watch, args):
    invoke, calls = watch
    assert invoke([], run_args=args).exit_code != 0
    assert not calls


def test_deadline_caps_sleep_and_no_get_at_deadline(watch, monkeypatch):
    clock = [10.0]
    waits = []

    class DeadlineStop(Event):
        def wait(self, timeout=None):
            waits.append(timeout)
            clock[0] += timeout
            return self.is_set()

    monkeypatch.setattr(actions_watch, "monotonic", lambda: clock[0])
    monkeypatch.setattr(actions_watch, "Event", DeadlineStop)
    invoke, calls = watch
    ret = invoke([{**ROW, "status": "RUNNING"}], "-i60", "--timeout", "2")
    assert ret.exit_code == 1 and "timed out" in ret.output
    assert len(calls) == 1 and waits == [2]


def test_stalled_get_does_not_hold_caller_past_deadline(watch):
    release, finished = Event(), Event()

    def stalled():
        try:
            assert release.wait(10), "watch joined the blocked read"
            return ROW
        finally:
            finished.set()

    invoke, calls = watch
    try:
        ret = invoke([stalled], "--timeout", "1", "--exit-status")
        assert ret.exit_code == 1 and "timed out" in ret.output and "COMPLETED" not in ret.output
        assert not finished.is_set() and len(calls) == 1
    finally:
        release.set()
        assert finished.wait(2)


def test_keyboard_interrupt_stops_local_wait_not_remote_run(watch, monkeypatch):
    worker_stopped = Event()

    class StopObserved(Event):
        def wait(self, timeout=None):
            stopped = super().wait(timeout)
            if stopped:
                worker_stopped.set()
            return stopped

    class InterruptOnUpdate(Queue):
        def get(self, *args, **kwargs):
            super().get(*args, **kwargs)
            raise KeyboardInterrupt

    monkeypatch.setattr(actions_watch, "Event", StopObserved)
    monkeypatch.setattr(actions_watch, "Queue", InterruptOnUpdate)
    invoke, calls = watch
    ret = invoke([{**ROW, "status": "RUNNING"}], "-i60")
    assert ret.exit_code == 130 and "interrupted locally" in ret.output
    assert worker_stopped.wait(2) and len(calls) == 1


def test_recheck_stop_after_deadline_preflight_before_get(watch, fast_poll, monkeypatch):
    clock = [10.0]
    worker_preflight, release = Event(), Event()
    workers = []
    worker_ticks = 0
    base_remaining = actions_watch._remaining

    def remaining(deadline):
        nonlocal worker_ticks
        left = base_remaining(deadline)
        if current_thread().name == "gc-run-watch":
            worker_ticks += 1
            if worker_ticks == 4:  # second preflight: check already made, GET not yet admitted
                worker_preflight.set()
                assert release.wait(4), "the caller did not exit on its own deadline"
        return left

    class DeadlineQueue(Queue):
        reads = 0

        def get(self, *args, **kwargs):
            self.reads += 1
            if self.reads == 2:  # after the first RUNNING observation was consumed
                assert worker_preflight.wait(2)
                clock[0] = 20.0
                return super().get(timeout=0)
            return super().get(*args, **kwargs)

    def record_worker(*args, **kwargs):
        worker = Thread(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(actions_watch, "monotonic", lambda: clock[0])
    monkeypatch.setattr(actions_watch, "_remaining", remaining)
    monkeypatch.setattr(actions_watch, "Queue", DeadlineQueue)
    monkeypatch.setattr(actions_watch, "Thread", record_worker)
    invoke, calls = watch
    try:
        ret = invoke([{**ROW, "status": "RUNNING"}], "--timeout", "5")
        assert ret.exit_code == 1 and "timed out" in ret.output and worker_preflight.is_set()
    finally:
        release.set()
        for worker in workers:
            worker.join(2)
    assert len(workers) == 1 and not workers[0].is_alive()
    assert len(calls) == 1 and fast_poll == [3]


def test_terminal_is_not_published_before_close(watch, monkeypatch):
    def failed_close(self):
        raise NetworkError("Synthetic transport close failed.")

    monkeypatch.setattr(ActionsClient, "close", failed_close)
    invoke, calls = watch
    ret = invoke([ROW])
    assert ret.exit_code == 1 and "Synthetic transport close failed." in ret.output
    assert "COMPLETED" not in ret.output and len(calls) == 1
