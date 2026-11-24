"""Bounded GitCode Actions reads and explicit single-target operations."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from unicodedata import category

from ..actions_client import UNCERTAIN, ActionsClient, segment
from ..errors import APIError, NetworkError

RUN_FIELDS = (
    "workflow_run_id",
    "workflow_id",
    "workflow_name",
    "run_number",
    "title",
    "event",
    "status",
    "head_sha",
    "head_branch",
    "attempt",
    "file_path",
)
MAX_PAGE = 100
MAX_WORKFLOW_SCAN = 500
SHA_RE = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
MAX_LOG = 128 * 1024


def pick(item: dict, keys: tuple[str, ...]) -> dict:
    """Never relay input/env/context/config blobs from pipeline detail responses."""
    return {k: item[k] for k in keys if isinstance(item.get(k), (str, int, bool))}


def nonnegative(value: Any) -> bool:
    return type(value) is int and value >= 0


def _rows(data: dict, key: str, limit: int | None = None) -> list[dict]:
    rows = data.get(key)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise APIError(f"Invalid Actions collection: {key}.")
    if limit is not None and len(rows) > limit:
        raise APIError("Actions returned more entries than requested.")
    return rows


def _snapshot_text(value: object, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value)
    ):
        raise APIError(f"Missing, invalid or oversized Actions snapshot field: {field}.")
    return value


def _snapshot_id(value: object) -> str:
    identifier = _snapshot_text(value, "id", 255)
    segment(identifier)  # Validate the native identifier; return its unescaped form.
    return identifier


def _snapshot_label(row: dict, seen: set[str], kind: str) -> dict[str, str]:
    """Only documented native identifiers, display names and status; no logs or job configuration."""
    identifier = _snapshot_id(row.get("id"))
    if identifier in seen:
        raise APIError(f"Duplicate Actions snapshot {kind} ID.")
    seen.add(identifier)
    return {
        "id": identifier,
        "name": _snapshot_text(row.get("name"), "name", 512),
        "status": _snapshot_text(row.get("status"), "status", 64),
    }


def _snapshot_steps(rows: list[dict], included: bool) -> list[dict[str, str]]:
    seen: set[str] = set()
    result = []
    for row in rows:
        step = _snapshot_label(row, seen, "step")
        if included:
            result.append(step)
    return result


def _snapshot_window(data: dict, offset: int, limit: int) -> dict:
    jobs = []
    total = step_count = 0
    stage_ids: set[str] = set()
    job_ids: set[str] = set()
    for stage in _rows(data, "stages"):
        stage_label = _snapshot_label(stage, stage_ids, "stage")
        for job in _rows(stage, "jobs"):
            job_label = _snapshot_label(job, job_ids, "job")
            rows = _rows(job, "steps")
            included = offset <= total < offset + limit
            if included:
                step_count += len(rows)
                if step_count > MAX_PAGE:
                    raise APIError("Snapshot exceeds 100 steps per page; lower --limit or inspect one job with --job.")
            steps = _snapshot_steps(rows, included)
            if included:
                jobs.append({**job_label, "stage": stage_label, "steps": steps})
            total += 1
    return {"jobs": jobs, "total_count": total, "next_offset": offset + limit if offset + limit < total else None}


class ActionsService:
    def __init__(self, client: ActionsClient, owner: str, repo: str):
        self.client = client
        self.owner = owner
        self.repo = repo

    def _call(self, op: str, **kwargs: Any) -> dict:
        return self.client.call(op, self.owner, self.repo, **kwargs)

    def pull(self, number: int) -> dict:
        if type(number) is not int or number < 1:
            raise APIError("Invalid PR number.")
        return self._call("pull", ids={"number": str(number)})

    def page(self, kind: str, page: int, per_page: int, **filters: Any) -> dict:
        if not 1 <= per_page <= MAX_PAGE or page < 1 or kind not in {"runs", "workflows"}:
            raise APIError("Invalid Actions page.")
        rows_key = "workflow_runs" if kind == "runs" else kind
        keys = RUN_FIELDS if kind == "runs" else ("workflow_id", "file_path", "name", "state")
        data = self._call(kind, params={"page": page, "per_page": per_page, **filters})
        rows = _rows(data, rows_key, per_page)
        total = data.get("total_count")
        offset = (page - 1) * per_page
        if (
            type(total) is not int
            or total < 0
            or (rows and total < offset + len(rows))
            or len(rows) < min(per_page, total - offset)
        ):
            raise APIError("Inconsistent Actions pagination; repeat the read.")
        return {
            rows_key: [pick(row, keys) for row in rows],
            "total_count": total,
            "page": page,
            "next_page": page + 1 if page * per_page < total else None,
        }

    def _workflow_rows(self, budget: int) -> Iterator[dict]:
        if not 1 <= budget <= MAX_WORKFLOW_SCAN:
            raise APIError(f"Workflow lookup limit must be between 1 and {MAX_WORKFLOW_SCAN}.")
        total = None
        page = 1
        size = min(MAX_PAGE, budget)
        while True:
            data = self.page("workflows", page, size)
            count = data["total_count"]
            if count > budget:
                raise APIError("Workflow lookup incomplete; increase --scan-limit or inspect workflow list --page.")
            if total is not None and count != total:
                raise APIError("Workflow listing changed during lookup; repeat the read.")
            total = count
            yield from data["workflows"]
            next_page = data["next_page"]
            if next_page is None:
                return
            page = next_page

    def workflow(self, selector: str, budget: int) -> dict:
        if not selector.strip() or len(selector) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in selector):
            raise APIError("Supply a nonempty workflow ID, name, or configuration filename.")
        matches: list[dict] = []
        id_match: dict | None = None
        seen: set[str] = set()
        for row in self._workflow_rows(budget):
            wid, path, name = (row.get(key) for key in ("workflow_id", "file_path", "name"))
            if not isinstance(wid, str) or not wid or wid in seen:
                raise APIError("Missing or repeated workflow ID; cannot verify listing.")
            if not isinstance(path, str) or not path or not isinstance(name, str):
                raise APIError("Incomplete workflow metadata; cannot resolve selector.")
            seen.add(wid)
            if selector == wid:
                id_match = row
            elif selector in {path, name, path.rsplit("/", 1)[-1]}:
                matches.append(row)
        if id_match is not None:
            return id_match
        if not matches:
            raise APIError("No matching workflow definition in this repository.")
        if len(matches) != 1:
            raise APIError("Ambiguous workflow selector; use the exact ID from workflow list.")
        return matches[0]

    def _read_run(self, run_id: str) -> dict:
        data = self._call("run", ids={"run_id": run_id})
        if data.get("workflow_run_id") != run_id:
            raise APIError("Actions returned a different or missing run ID.")
        return data

    def detail(self, run_id: str) -> dict:
        return pick(self._read_run(run_id), RUN_FIELDS)

    @staticmethod
    def _check_pin(detail: dict, attempt: int | None, commit: str | None) -> None:
        sha = detail.get("head_sha")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha) or not nonnegative(detail.get("attempt")):
            raise APIError("Cannot verify the exact Actions commit and attempt.")
        if attempt is not None and detail["attempt"] != attempt or commit is not None and sha.lower() != commit.lower():
            raise APIError("Actions run no longer matches the requested commit/attempt.")

    def pin(self, run_id: str, attempt: int | None = None, commit: str | None = None) -> dict:
        detail = self.detail(run_id)
        self._check_pin(detail, attempt, commit)
        return detail

    def job_snapshot(self, run_id: str, attempt: int | None, commit: str | None, offset: int, limit: int) -> dict:
        """One run observation: pin and project the same response, never join different reads."""
        if offset < 0 or not 1 <= limit <= MAX_PAGE:
            raise APIError("Invalid result window.")
        data = self._read_run(_snapshot_id(run_id))
        self._check_pin(data, attempt, commit)
        return {
            "run": pick(data, ("workflow_run_id", "attempt", "head_sha")),
            **_snapshot_window(data, offset, limit),
        }

    def _jobs(self, run_id: str) -> list[dict]:
        data = self._call("jobs", ids={"run_id": run_id})
        rows = _rows(data, "jobs")
        total = data.get("total_count")
        if not nonnegative(total) or total != len(rows):
            raise APIError("Incomplete job list; the upstream API has no job pagination.")
        return rows

    def jobs(self, run_id: str, offset: int, limit: int) -> dict:
        return self._window(self._jobs(run_id), ("id", "name", "status"), offset, limit, "jobs")

    @staticmethod
    def _window(rows: list[dict], keys: tuple[str, ...], offset: int, limit: int, name: str) -> dict:
        if offset < 0 or not 1 <= limit <= MAX_PAGE:
            raise APIError("Invalid result window.")
        return {
            name: [pick(row, keys) for row in rows[offset : offset + limit]],
            "total_count": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
        }

    def job(self, run_id: str, job_id: str) -> dict:
        data = self._call("job", ids={"run_id": run_id, "job_id": job_id})
        if data.get("id") != job_id:
            raise APIError("Actions returned a different or missing job ID.")
        return data

    def steps(self, job: dict, offset: int, limit: int) -> dict:
        return {
            **pick(job, ("id", "name", "status")),
            **self._window(_rows(job, "steps"), ("id", "job_run_id", "name", "status"), offset, limit, "steps"),
        }

    def logs(self, run_id: str, job: dict, step: str, offset: int, limit: int, sort: str) -> dict:
        if offset < 0 or not 1 <= limit <= MAX_PAGE or sort not in {"asc", "desc"}:
            raise APIError("Invalid log query.")
        if not any(row.get("id") == step for row in _rows(job, "steps")):
            raise APIError("Step ID not present in the selected job.")
        data = self._call(
            "logs",
            ids={"run_id": run_id, "job_id": job["id"]},
            body={"step_id": step, "offset": offset, "limit": limit, "sort": sort},
        )
        text, more = data.get("log"), data.get("has_more")
        start, end = data.get("start_offset"), data.get("end_offset")
        if (
            not isinstance(text, str)
            or not isinstance(more, bool)
            or not nonnegative(start)
            or not nonnegative(end)
            or end < start
        ):
            raise APIError("Malformed log page.")
        if len(text.encode("utf-8", errors="surrogatepass")) > MAX_LOG:
            raise APIError("Log page too large; request fewer entries. No log cursor was advanced.")
        cursor = end if sort == "asc" else start
        if more and (cursor <= offset if sort == "asc" else (offset != 0 and cursor >= offset) or cursor == 0):
            raise APIError("Log cursor did not advance.")
        return {
            "job_id": job["id"],
            "step_id": step,
            "log": text,
            "has_more": more,
            "start_offset": start,
            "end_offset": end,
            "next_offset": cursor if more else None,
            "sort": sort,
        }

    def dispatch(self, workflow_id: str, ref: str, inputs: dict[str, str]) -> dict:
        if not ref.strip():
            raise APIError("An explicit branch or tag is required.")
        data = self._call("dispatch", ids={"workflow_id": workflow_id}, body={"ref": ref, "inputs": inputs})
        if not all(isinstance(data.get(k), str) and data[k] for k in ("workflow_id", "workflow_run_id")) or (
            not workflow_id.endswith((".yml", ".yaml")) and data["workflow_id"] != workflow_id
        ):
            raise APIError("Unconfirmed workflow dispatch." + UNCERTAIN)
        return {**pick(data, ("workflow_id", "workflow_run_id")), "requested_ref": ref, "result": "requested"}

    def cancel(self, run_id: str, attempt: int, commit: str) -> dict:
        self.client.require_token()
        if not SHA_RE.fullmatch(commit) or not nonnegative(attempt):
            raise APIError("A full hexadecimal commit SHA and nonnegative attempt are required.")
        before = self.pin(run_id, attempt, commit)
        if before.get("status") == "CANCELED":
            return {"result": "already_canceled", "run": before}
        if before.get("status") != "RUNNING":
            raise APIError("Only a run that the server reports as RUNNING can be stopped.")
        result = self._call("stop", ids={"run_id": run_id})
        if result.get("success") is not True:
            raise APIError("Unconfirmed stop response." + UNCERTAIN)
        try:
            after = self.pin(run_id, attempt, commit)
        except (APIError, NetworkError) as exc:
            raise APIError("Stop requested, but read-back could not verify the same run attempt." + UNCERTAIN) from exc
        if after.get("status") == "CANCELED":
            return {"result": "canceled", "run": after}
        return {
            "result": "requested_not_confirmed",
            "run": after,
            "verify": "Re-read the same run and attempt; do not automatically retry.",
        }

    def rerun(self, run_id: str, attempt: int, commit: str, job_run_ids: tuple[str, ...]) -> dict:
        self.client.require_token()
        if len(set(job_run_ids)) != len(job_run_ids) or len(job_run_ids) > MAX_PAGE:
            raise APIError("Supply at most 100 distinct failed job-run IDs.")
        for job_run_id in job_run_ids:
            segment(job_run_id)
        run = self.pin(run_id, attempt, commit)
        ids = {"run_id": run_id}
        if job_run_ids:
            jobs = self._jobs(run_id)
            for selected in job_run_ids:
                matches = [job for job in jobs if job.get("exec_id") == selected]
                if len(matches) != 1 or matches[0].get("status") != "FAILED":
                    raise APIError("Cannot verify a unique failed job for the supplied execution ID.")
                job = matches[0]
                job_id = job.get("id")
                if not isinstance(job_id, str) or not job_id or sum(row.get("id") == job_id for row in jobs) != 1:
                    raise APIError("Cannot verify the failed job's identity.")
                steps = _rows(job, "steps")
                if not steps or any(step.get("job_run_id") != selected for step in steps):
                    raise APIError("Cannot verify the supplied execution ID against the failed job's steps.")
            self.pin(run_id, attempt, commit)
            result = self._call("retry", ids=ids, body={"job_run_ids": list(job_run_ids)})
        else:
            result = self._call("rerun", ids=ids)
        if result.get("success") is not True:
            raise APIError("Unconfirmed rerun request." + UNCERTAIN)
        return {
            "result": "requested",
            "prior_run": run,
            "scope": list(job_run_ids) or "entire_run",
            "verify": "Re-read the run list and detail to identify the new attempt; do not automatically retry.",
        }
