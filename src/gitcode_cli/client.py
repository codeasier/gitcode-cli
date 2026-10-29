from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin

import httpx

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
        merged_params: dict[str, Any] = {"access_token": self.token}
        if params:
            merged_params.update({k: v for k, v in params.items() if v is not None})
        headers = {"Accept": accept}
        if _requires_private_token(method, path):
            headers["private-token"] = self.token
        try:
            response = self._client.request(
                method,
                urljoin(self.base_url, path.lstrip("/")),
                params=merged_params,
                json=json,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise NetworkError(f"Request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise NetworkError(f"Connection failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise NetworkError(f"Network error: {exc}") from exc
        if response.status_code == 401:
            try:
                data = response.json()
                original = data.get("error_message") or data.get("message") or str(data)
            except Exception:
                original = response.text
            raise APIError(f"Authentication failed: {original}. Run 'gc auth login' to authenticate.", 401)
        if response.status_code >= 400:
            try:
                data = response.json()
                message = data.get("error_message") or data.get("message") or str(data)
            except Exception:
                message = response.text
            raise APIError(message or "GitCode API request failed", response.status_code)
        if not response.content:
            return None
        if response_format == "text":
            return response.text
        return response.json()

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
