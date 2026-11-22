"""CLI transport for the documented Actions v8 operations (not a general URL proxy)."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote, unquote

import httpx

from ._redact import redacted_transport
from .errors import APIError, NetworkError

# path, method, success code, business write (POSTing a log query is a read).
_ROUTES = {
    "pull": ("pulls/{number}", "GET", 200, False),
    "runs": ("runs", "GET", 200, False),
    "run": ("runs/{run_id}", "GET", 200, False),
    "jobs": ("runs/{run_id}/jobs", "GET", 200, False),
    "job": ("runs/{run_id}/jobs/{job_id}", "GET", 200, False),
    "logs": ("runs/{run_id}/jobs/{job_id}/logs", "POST", 200, False),
    "workflows": ("workflows", "GET", 200, False),
    "dispatch": ("workflows/{workflow_id}/dispatches", "POST", 201, True),
    "rerun": ("runs/{run_id}/rerun", "POST", 200, True),
    "stop": ("runs/{run_id}/stop", "POST", 200, True),
    "retry": ("runs/{run_id}/retry", "POST", 200, True),
    "run-artifacts": ("runs/{run_id}/artifacts", "GET", 200, False),
    "artifact": ("artifacts/{artifact_id}", "GET", 200, False),
    "artifact-zip": ("artifacts/{artifact_id}/zip", "GET", 302, False),
}
MAX_RESPONSE = 2 * 1024 * 1024
UNCERTAIN = " Verify remote runs and attempts before retrying; the request may already have taken effect."


def segment(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255 or value in {".", ".."}:
        raise APIError("Invalid Actions resource identifier.")
    if re.search(r"[/\\%?#:\s\x00-\x1f\x7f]", value):
        raise APIError("Invalid Actions resource identifier.")
    return quote(value, safe="")


def _contains_token(value: Any, token: str) -> bool:
    if isinstance(value, str):
        return token in value
    if isinstance(value, dict):
        return any(_contains_token(k, token) or _contains_token(v, token) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_token(v, token) for v in value)
    return False


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError("Duplicate Actions response field.")
    return data


def _body(response: httpx.Response, uncertain: str) -> dict[str, Any]:
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise APIError("Cannot safely bound a compressed Actions response." + uncertain)
    body = bytearray()
    for chunk in response.iter_bytes(64 * 1024):
        if len(body) + len(chunk) > MAX_RESPONSE:
            raise APIError("Actions response exceeded the byte limit; request a smaller page if possible." + uncertain)
        body.extend(chunk)
    try:
        data = json.loads(body, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise APIError("Invalid Actions JSON response." + uncertain) from None
    if not isinstance(data, dict):
        raise APIError("Expected an Actions response object." + uncertain)
    return data


class ActionsClient:
    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None):
        self._token = token
        self._http = httpx.Client(timeout=30.0, transport=transport, follow_redirects=False, trust_env=False)

    def close(self) -> None:
        self._http.close()

    def require_token(self) -> None:
        if not self._token:
            raise APIError("Authenticate with gc before requesting an Actions write.")

    def call(
        self,
        operation: str,
        owner: str,
        repo: str,
        *,
        ids: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if operation == "artifact-zip":
            raise APIError("Use the isolated Actions artifact transfer.")
        with self._response(operation, owner, repo, ids=ids, params=params, body=body) as (response, uncertain):
            return _body(response, uncertain)

    def artifact_zip(self, owner: str, repo: str, artifact_id: str, destination, size: int, sha256: str) -> None:
        from .actions_artifact_zip import stream_zip  # noqa: PLC0415

        with self._response("artifact-zip", owner, repo, ids={"artifact_id": artifact_id}) as (response, _):
            locations = response.headers.get_list("location")
            if len(locations) != 1:
                raise APIError("Actions did not return a unique artifact download location.")
            # Build the base without the request's query credential.
            base = str(response.request.url.copy_with(query=None))
        stream_zip(base, locations[0], destination, size, sha256, token=self._token)

    @contextmanager
    def _response(
        self,
        operation: str,
        owner: str,
        repo: str,
        *,
        ids: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ):
        template, method, status, write = _ROUTES[operation]
        if write:
            self.require_token()
        suffix = template.format(**{k: segment(v) for k, v in (ids or {}).items()})
        version, prefix = ("v5", "") if operation == "pull" else ("v8", "actions/")
        url = f"https://api.gitcode.com/api/{version}/repos/{segment(owner)}/{segment(repo)}/{prefix}{suffix}"
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if "access_token" in query:
            raise APIError("Use gc authentication, not an Actions query credential.")
        if self._token and (
            self._token in unquote(url) or _contains_token(query, self._token) or _contains_token(body, self._token)
        ):
            raise APIError("Refusing to include the active authentication token in Actions arguments.")
        if self._token:
            query["access_token"] = self._token
        uncertain = UNCERTAIN if write else ""
        try:
            self._http.cookies.clear()
            with (
                redacted_transport(self._token),
                self._http.stream(
                    method,
                    url,
                    params=query,
                    json=body,
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                ) as response,
            ):
                if response.status_code != status:
                    # Never echo server-supplied request data or log text in diagnostics.
                    raise APIError(
                        f"Actions {operation}: HTTP {response.status_code}." + uncertain, response.status_code
                    )
                yield response, uncertain
        except httpx.HTTPError:
            raise NetworkError(f"Actions {operation}: network error." + uncertain) from None
