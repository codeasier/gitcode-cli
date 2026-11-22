"""Read-only evidence about PR-associated Actions; never a merge decision."""

from __future__ import annotations

from typing import Any

from ..errors import APIError, NetworkError
from ..services.actions import SHA_RE, ActionsService, nonnegative


def _snapshot(actions: ActionsService, number: int) -> tuple[str | None, dict]:
    data = actions.pull(number)
    if not isinstance(data, dict) or str(data.get("number")) != str(number):
        raise APIError("Cannot verify the v5 PR identity.")
    head = data.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    gates = data.get("mergeable_state")
    gates = gates if isinstance(gates, dict) else {}
    rules = gates.get("merge_request_switch")
    rules = rules if isinstance(rules, dict) else {}

    def boolean(value: Any):
        return value if isinstance(value, bool) else None

    return (
        sha.lower() if isinstance(sha, str) and SHA_RE.fullmatch(sha) else None,
        {
            "source": "v5 PR detail",
            "can_merge_check": boolean(data.get("can_merge_check")),
            "mergeable": boolean(data.get("mergeable")),
            "ci_state_passed": boolean(gates.get("ci_state_passed")),
            "pipeline_required": boolean(rules.get("only_allow_merge_if_pipeline_succeeds")),
            "state": boolean(gates.get("state")),
        },
    )


def _candidates(actions: ActionsService, number: int, budget: int) -> tuple[list[dict], bool]:
    # Do not trust list ordering; retain the latest run_number per workflow across every inspected page.
    rows: list[dict] = []
    seen: set[str] = set()
    total: int | None = None
    size = min(25, budget)
    page = 1
    while True:
        data = actions.page("runs", page, size, event="MR", pull_request_id=str(number))
        batch = data["workflow_runs"]
        if total is not None and data["total_count"] != total:
            raise APIError("The Actions list changed during pagination; repeat the read.")
        total = data["total_count"]
        for row in batch:
            identifier = row.get("workflow_run_id")
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                raise APIError("Invalid or repeated Actions run ID.")
            seen.add(identifier)
        rows.extend(batch[: budget - len(rows)])
        if data["next_page"] is None or len(rows) >= budget:
            return rows, len(rows) == total
        page += 1


def _latest(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        wf, seq = row.get("workflow_id"), row.get("run_number")
        if not isinstance(wf, str) or not wf or not nonnegative(seq) or row.get("event") != "MR":
            raise APIError("Cannot verify workflow identity/order or PR event in v8 results.")
        if wf not in latest or seq > latest[wf]["run_number"]:
            latest[wf] = row
        elif seq == latest[wf]["run_number"]:
            raise APIError("Ambiguous most recent Actions run number.")
    return latest


def _observations(actions: ActionsService, head: str, rows: list[dict]) -> list[dict]:
    observations = []
    for row in _latest(rows).values():
        listed_sha = row.get("head_sha")
        if not isinstance(listed_sha, str) or listed_sha.lower() != head:
            # The v8 list has no authoritative merge-ref -> source-head identity map.
            observations.append({"identity": "different_or_unverifiable_sha", "run": row})
            continue
        run = actions.pin(row["workflow_run_id"], commit=head)
        if any(run.get(k) != row[k] for k in ("workflow_id", "run_number", "event")):
            raise APIError("Run identity changed between list and detail.")
        observations.append({"identity": "exact_head", "run": run})
    return observations


def _outcome(observations: list[dict], complete: bool) -> str:
    if not complete:
        return "incomplete_scan"
    if not observations:
        return "no_observed_runs"
    if any(o["identity"] != "exact_head" for o in observations):
        return "unknown_revision"
    statuses = {o["run"].get("status") for o in observations}
    if statuses.intersection({"FAILED", "CANCELED"}):
        return "failed_or_canceled"
    if statuses.intersection({"RUNNING", "PAUSED", "SUSPEND"}):
        return "pending"
    return "observed_completed" if statuses == {"COMPLETED"} else "unknown_status"


def _run_signatures(rows: list[dict]) -> dict[str, tuple]:
    keys = ("workflow_id", "run_number", "head_sha", "event", "attempt", "status")
    return {row["workflow_run_id"]: tuple(row.get(k) for k in keys) for row in rows}


def _unchanged(
    actions: ActionsService, number: int, budget: int, head: str, rows: list[dict], runs: list[dict]
) -> bool:
    final_rows, complete = _candidates(actions, number, budget)
    if not complete or _run_signatures(final_rows) != _run_signatures(rows):
        return False
    current = _observations(actions, head, final_rows)
    return _run_signatures([item["run"] for item in current]) == _run_signatures([item["run"] for item in runs])


def pr_evidence(actions: ActionsService, number: int, budget: int) -> dict:
    if not 1 <= budget <= 100:
        raise APIError("PR checks scan limit must be between 1 and 100 runs.")
    head, gates = _snapshot(actions, number)
    result: dict = {
        "pr": number,
        "head_sha": head,
        "reported_gates": gates,
        "observed_actions": {"source": "v8 MR runs and current run details", "runs": []},
        "scope": "Observed PR workflows only; not an inventory of required checks or permission to merge.",
    }
    if not head:
        result["outcome"] = "unknown_head"
        return result
    observed = result["observed_actions"]
    try:
        rows, complete = _candidates(actions, number, budget)
        observed.update(scanned=len(rows), complete=complete, exact_head_only=True)
        observed["runs"] = _observations(actions, head, rows)
        observed["outcome"] = result["outcome"] = _outcome(observed["runs"], complete)
        if result["outcome"] == "observed_completed":
            if not _unchanged(actions, number, budget, head, rows, observed["runs"]):
                result["outcome"] = "actions_changed"
            else:
                observed["stable_on_reread"] = True
    except (APIError, NetworkError) as exc:
        # Preserve useful v5 gates even when this account/installation cannot read Actions.
        result["outcome"] = (
            "actions_unavailable"
            if isinstance(exc, APIError) and exc.status_code in {401, 403, 404, 405, 501}
            else "unknown"
        )
        observed["error"] = str(exc)
    final_head, final_gates = _snapshot(actions, number)
    result.update(head_sha=final_head, reported_gates=final_gates)
    if final_head != head:
        result["outcome"] = "head_changed"
        observed["observed_for_sha"] = head
    elif result["outcome"] == "observed_completed":
        if final_gates["pipeline_required"] is True and final_gates["ci_state_passed"] is False:
            result["outcome"] = "ci_gate_not_passed"
        elif not all(g["pipeline_required"] is True and g["ci_state_passed"] is True for g in (gates, final_gates)):
            result["outcome"] = "ci_gate_unverified"
    return result
