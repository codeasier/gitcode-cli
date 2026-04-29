from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from .errors import APIError, NetworkError

BASE_URL = "https://api.gitcode.com/api/v5/"


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
        try:
            response = self._client.request(
                method,
                urljoin(self.base_url, path.lstrip("/")),
                params=merged_params,
                json=json,
                headers={"Accept": accept},
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
                original = data.get("message") or str(data)
            except Exception:
                original = response.text
            raise APIError(f"Authentication failed: {original}. Run 'gc auth login' to authenticate.", 401)
        if response.status_code >= 400:
            try:
                data = response.json()
                message = data.get("message") or str(data)
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
