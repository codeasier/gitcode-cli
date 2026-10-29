from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from ._redact import redact, redacted_transport
from .errors import APIError, NetworkError

BASE_URL = "https://api.gitcode.com/api/v5/"


def _requires_private_token(method: str, path: str) -> bool:
    """CLI-only repository auth policy; shared services never handle credentials."""
    parts = path.strip("/").split("/")
    method = method.upper()
    if parts == ["user", "repos"]:
        return method in {"GET", "POST"}
    if len(parts) == 3 and parts[0] in {"users", "orgs"} and parts[2] == "repos":
        return method == "GET" or (parts[0] == "orgs" and method == "POST")
    if len(parts) < 3 or parts[0] != "repos":
        return False
    if len(parts) == 3:
        # POST /repos/:owner/issues is issue creation, not a repository call.
        return method in {"GET", "PATCH", "DELETE"}
    if parts[3] == "contents" and len(parts) > 4:
        return method == "GET"
    return len(parts) == 4 and (method, parts[3]) in {("POST", "forks"), ("PUT", "sync_repo")}


class GitCodeClient:
    def __init__(self, token: str, base_url: str = BASE_URL):
        self.token = token
        self.base_url = base_url
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        """Release transport resources for long-lived service consumers."""
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        response_format: Literal["json", "text"] = "json",
    ) -> Any | None:
        merged_params: dict[str, Any] = {k: v for k, v in (params or {}).items() if v is not None}
        merged_params["access_token"] = self.token
        headers = {"Accept": accept}
        if _requires_private_token(method, path):
            headers["private-token"] = self.token
        uncertain = " Verify the remote state before retrying this write." if method.upper() != "GET" else ""
        try:
            with redacted_transport(self.token):
                response = self._client.request(
                    method,
                    urljoin(self.base_url, path.lstrip("/")),
                    params=merged_params,
                    json=json,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            label = "Network error"
            if isinstance(exc, httpx.TimeoutException):
                label = "Request timed out"
            elif isinstance(exc, httpx.ConnectError):
                label = "Connection failed"
            raise NetworkError(f"{label}: {redact(exc, self.token)}{uncertain}") from None
        if (
            method.upper() == "DELETE"
            and len(path.strip("/").split("/")) == 3
            and path.lstrip("/").startswith("repos/")
            and 200 <= response.status_code < 300
            and response.status_code not in {200, 204}
        ):
            raise APIError("Repository deletion was not confirmed." + uncertain, response.status_code)
        return self._decode_response(response, response_format, uncertain)

    def _decode_response(self, response: httpx.Response, response_format: str, uncertain: str) -> Any | None:
        if not 200 <= response.status_code < 300 or response.status_code == 202:
            try:
                data = response.json()
                message = data.get("error_message") or data.get("message") or str(data)
            except Exception:
                message = response.text
            message = redact(message or "GitCode API request failed", self.token)
            if response.status_code == 401:
                message = f"Authentication failed: {message}. Run 'gc auth login' to authenticate."
            raise APIError(message + uncertain, response.status_code)
        if response_format == "text":
            return response.text
        if not response.content:
            if response.status_code in {204, 205}:
                return None
            raise APIError("Empty API response." + uncertain, response.status_code)
        try:
            result = response.json()
        except ValueError:
            raise APIError("Invalid JSON API response." + uncertain, response.status_code) from None
        if result is None:
            raise APIError("Null API response." + uncertain, response.status_code)
        return result

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any | None:
        return self.request("GET", path, params=params)

    def post(
        self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any | None:
        return self.request("POST", path, params=params, json=json)

    def patch(
        self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any | None:
        return self.request("PATCH", path, params=params, json=json)

    def put(self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> Any | None:
        return self.request("PUT", path, params=params, json=json)

    def delete(
        self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any | None:
        return self.request("DELETE", path, params=params, json=json)
