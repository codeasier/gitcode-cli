"""Read one current GitCode run attempt, not PR merge gates."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic

from .errors import APIError
from .services.actions import ActionsService

ACTIVE = {"RUNNING", "PAUSED", "SUSPEND"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELED", "IGNORED"}
MAX_INTERVAL = 60
MAX_TIMEOUT = 900
_TIMEOUT = "Watch timed out locally without a verified terminal observation; no stop request was sent."


def _remaining(deadline: float) -> float:
    left = deadline - monotonic()
    if left <= 0:
        raise APIError(_TIMEOUT)
    return left


def watch_run(
    open_service: Callable[[], AbstractContextManager[ActionsService]],
    run_id: str,
    interval: int,
    timeout: int,
    progress: Callable[[str], None],
) -> dict:
    """Use one GET at a time. A late/stalled synchronous read cannot extend the CLI deadline."""
    if not 1 <= interval <= MAX_INTERVAL or not 1 <= timeout <= MAX_TIMEOUT:
        raise APIError("Invalid run watch interval or timeout.")
    deadline = monotonic() + timeout
    stopped = Event()
    events: Queue[dict | Exception] = Queue()

    def poll() -> None:
        # Only this worker owns the synchronous client. It closes it even if the caller
        # stopped waiting mid-read. Never join a stalled HTTP/DNS read on CLI shutdown.
        previous = commit = attempt = None
        try:
            with open_service() as service:
                while True:
                    _remaining(deadline)
                    # Admit the poll only after checking the deadline and then the stop
                    # flag. An admitted read may still be scheduled or in flight on exit.
                    if stopped.is_set():
                        return
                    row = service.pin(run_id, attempt, commit)
                    _remaining(deadline)
                    attempt, commit = row["attempt"], row["head_sha"]
                    status = row.get("status")
                    if status not in ACTIVE and status not in TERMINAL:
                        raise APIError("Missing or unrecognized GitCode run status; watch stopped.")
                    if stopped.is_set():
                        return
                    observation = {key: row[key] for key in ("workflow_run_id", "head_sha", "attempt", "status")}
                    if status in TERMINAL:
                        break
                    if status != previous:
                        events.put(observation)
                    previous = status
                    if stopped.wait(min(interval, _remaining(deadline))):
                        return
            # Successful observations are final only after the transport closes.
            if not stopped.is_set():
                events.put(observation)
        except Exception as exc:
            events.put(exc)

    try:
        Thread(target=poll, daemon=True, name="gc-run-watch").start()
        while True:
            try:
                # A finite wait also lets the main thread process console interrupts on Windows.
                event = events.get(timeout=min(_remaining(deadline), 0.25))
            except Empty:
                continue
            _remaining(deadline)
            if isinstance(event, Exception):
                raise event
            status = event["status"]
            if status in TERMINAL:
                return event
            progress(status)
    finally:
        stopped.set()
