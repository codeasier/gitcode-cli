"""Artifact provenance from the documented Actions v8 run list and detail."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..actions_artifact_zip import MAX_ZIP_BYTES, preflight_output, verified_output
from ..actions_client import segment
from ..errors import APIError
from .actions import MAX_PAGE, SHA_RE, ActionsService, nonnegative, pick

_FIELDS = (
    "id",
    "name",
    "size_bytes",
    "workflow_id",
    "workflow_run_id",
    "digest",
    "expires_at",
    "created_at",
    "updated_at",
)
_NULLABLE_TIMESTAMPS = ("expires_at", "created_at", "updated_at")
_MAX_SCAN_PAGES = 20
_DIGEST = re.compile(r"(?:sha256:)?([0-9a-fA-F]{64})\Z")


def _identity(row: dict, run: dict, *, from_list: bool = False) -> dict:
    artifact_id = row.get("id")
    if (
        not isinstance(artifact_id, str)
        or not isinstance(row.get("name"), str)
        or not row["name"]
        or row.get("workflow_run_id") != run["workflow_run_id"]
        or row.get("workflow_id") != run["workflow_id"]
    ):
        raise APIError("Cannot verify artifact identity against this workflow/run.")
    segment(artifact_id)
    if (
        not nonnegative(row.get("size_bytes"))
        or not isinstance(row.get("digest"), str)
        or any(
            (from_list and key not in row) or (row.get(key) is not None and not isinstance(row[key], str))
            for key in _NULLABLE_TIMESTAMPS
        )
    ):
        raise APIError("Invalid Actions artifact metadata: expected a byte count, digest and nullable timestamps.")
    return pick(row, _FIELDS)


def _expiry_millis(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        if re.fullmatch(r"[0-9]{1,13}", value):
            return float(value)
        if len(value) <= 64:
            try:
                stamp = datetime.fromisoformat(value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value)
                if stamp.tzinfo is not None:
                    return stamp.timestamp() * 1000
            except (ValueError, OSError, OverflowError):
                pass
    raise APIError("Artifact expiration metadata is not verifiable.")


def _integrity(row: dict) -> tuple[int, str]:
    size = row.get("size_bytes")
    digest = row.get("digest")
    match = _DIGEST.fullmatch(digest) if isinstance(digest, str) else None
    if type(size) is not int or not 22 <= size <= MAX_ZIP_BYTES or match is None:
        raise APIError("Artifact requires a ZIP size within 512 MiB and a valid SHA-256 in both metadata responses.")
    expiration = _expiry_millis(row.get("expires_at"))
    if expiration is not None and expiration <= time.time() * 1000:
        raise APIError("Artifact metadata reports that it has expired.")
    return size, match[1].lower()


class ActionsArtifactService:
    def __init__(self, svc: ActionsService):
        self.svc = svc

    def _pin(self, run_id: str, attempt: int | None = None, commit: str | None = None) -> dict:
        if commit is not None and not SHA_RE.fullmatch(commit):
            raise APIError("Specify a full 40- or 64-hex commit SHA.")
        current = self.svc.pin(run_id, attempt, commit)
        workflow_id = current.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id:
            raise APIError("Actions run did not identify its workflow.")
        segment(workflow_id)
        return current

    def _repin(self, run: dict) -> None:
        latest = self._pin(run["workflow_run_id"], run["attempt"], run["head_sha"])
        if latest["workflow_id"] != run["workflow_id"]:
            raise APIError("Actions workflow changed while checking artifacts.")

    def _page(self, run: dict, page: int, limit: int) -> dict:
        if not 1 <= limit <= MAX_PAGE or not 1 <= page <= 100:
            raise APIError("Invalid artifact page.")
        result = self.svc.client.call(
            "run-artifacts",
            self.svc.owner,
            self.svc.repo,
            ids={"run_id": run["workflow_run_id"]},
            params={"page": page, "per_page": limit, "sort": "created", "direction": "asc"},
        )
        rows = result.get("artifacts")
        total = result.get("total_count")
        offset = (page - 1) * limit
        if (
            not isinstance(total, int)
            or not nonnegative(total)
            or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or len(rows) != min(limit, max(0, total - offset))
        ):
            raise APIError("Invalid or incomplete Actions artifact page.")
        artifacts = [_identity(row, run, from_list=True) for row in rows]
        if len({row["id"] for row in artifacts}) != len(artifacts):
            raise APIError("Duplicate artifact ID in one Actions page.")
        return {
            "artifacts": artifacts,
            "total_count": total,
            "page": page,
            "next_page": page + 1 if offset + len(rows) < total else None,
        }

    def list(self, run_id: str, page: int, limit: int, attempt: int | None, commit: str | None) -> dict:
        run = self._pin(run_id, attempt, commit)
        result = self._page(run, page, limit)
        self._repin(run)
        # Artifact objects carry a run ID, not an attempt. Only an observed
        # first attempt lets us correlate the returned rows without guessing.
        return {"run": run, "artifact_attempt": 1 if run["attempt"] == 1 else None, **result}

    def _find(self, run: dict, selector: str, *, by_name: bool = False) -> tuple[dict, dict[str, bytes]]:
        # Bound memory across pages. Name selection compares both complete observations;
        # key by ID rather than relying on the provider's ordering for tied creation times.
        seen: dict[str, bytes] = {}
        selected = None
        total = None
        for page in range(1, _MAX_SCAN_PAGES + 1):
            result = self._page(run, page, MAX_PAGE)
            if total is None:
                total = result["total_count"]
            if total is None or total != result["total_count"] or total > _MAX_SCAN_PAGES * MAX_PAGE:
                raise APIError("Artifact list changed or exceeded the bounded scan; no archive was installed.")
            for item in result["artifacts"]:
                identity = item["id"]
                if identity in seen:
                    raise APIError("Artifact list has overlapping pages; repeat the read.")
                seen[identity] = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).digest() if by_name else b""
                if (item["name"] if by_name else identity) == selector:
                    if selected is not None:
                        raise APIError("More than one artifact has the exact name on this run; use --artifact-id.")
                    selected = item
            if result["next_page"] is None:
                if selected is None:
                    raise APIError("The exact artifact selector is not present on this run.")
                return selected, seen
        raise APIError("Artifact list exceeded the bounded scan; no archive was installed.")

    def _detail(self, run: dict, artifact_id: str, listed: dict) -> tuple[int, str]:
        result = self.svc.client.call("artifact", self.svc.owner, self.svc.repo, ids={"artifact_id": artifact_id})
        item = _identity(result, run)
        observed = _integrity(item)
        if item["id"] != artifact_id or item["name"] != listed["name"] or observed != _integrity(listed):
            raise APIError("Artifact list and detail disagree; no archive was installed.")
        return observed

    def download(
        self, run_id: str, artifact_id: str | None, attempt: int, commit: str, output: Path, *, name: str | None = None
    ) -> dict:
        if name is not None:
            if artifact_id is not None or not name.strip() or len(name) > 1024 or not name.isprintable():
                raise APIError("Use one nonempty printable exact artifact name (at most 1024 characters), or an ID.")
            selector = name
        elif artifact_id is not None:
            segment(artifact_id)
            selector = artifact_id
        else:
            raise APIError("Specify an exact artifact ID or name.")
        if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
            raise APIError("Specify a full 40- or 64-hex commit SHA.")
        if type(attempt) is not int or attempt != 1:
            raise APIError("GitCode artifacts have no attempt field; download is limited to a verified first attempt.")
        with preflight_output(output) as (absolute, directory):
            run = self._pin(run_id, attempt, commit)
            listed, observed = self._find(run, selector, by_name=name is not None)
            selected_id = listed["id"]
            size, sha256 = self._detail(run, selected_id, listed)
            self._repin(run)
            with verified_output(absolute, directory) as stage:
                self.svc.client.artifact_zip(self.svc.owner, self.svc.repo, selected_id, stage, size, sha256)
                if name is not None:
                    _, latest = self._find(run, name, by_name=True)
                    if latest != observed:
                        raise APIError("Artifact listing changed during name selection; no archive was installed.")
                self._detail(run, selected_id, listed)
                self._repin(run)
        return {
            "run": run,
            "artifact_id": selected_id,
            "artifact_attempt": attempt,
            "size_bytes": size,
            "sha256": sha256,
            "output": str(output),
        }
