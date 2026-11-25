from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from ._redact import redact, redacted_transport
from .errors import APIError, ConfigError, NetworkError
from .rest_api import validate_bearer_target

BASE_URL = "https://api.gitcode.com/api/v5/"
ISSUE_STATUS_PAGE_SIZE = 50
ISSUE_STATUS_MAX_PAGE = 11  # Ten data pages plus the terminal probe.
_STATUS_ROUTE = re.compile(
    r"/user|/repos/[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}(?P<queue>/issues)?"
)
_STATUS_PAGE_FIELDS = frozenset({"state", "page", "per_page"})
ISSUE_STATUS_LOGIN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}")


def _valid_status_query(params: dict[str, str]) -> bool:
    filters = params.keys() - _STATUS_PAGE_FIELDS
    if len(filters) != 1 or not _STATUS_PAGE_FIELDS.issubset(params):
        return False
    actor = filters.pop()
    if actor not in {"assignee", "creator"}:
        return False
    page = params["page"]
    return (
        params["state"] == "open"
        and params["per_page"] == str(ISSUE_STATUS_PAGE_SIZE)
        and re.fullmatch(r"[1-9][0-9]?", page) is not None
        and int(page) <= ISSUE_STATUS_MAX_PAGE
        and ISSUE_STATUS_LOGIN.fullmatch(params[actor]) is not None
    )


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
    def __init__(self, token: str, base_url: str = BASE_URL, *, transport: httpx.BaseTransport | None = None):
        self.token = token
        self.base_url = base_url
        if transport is not None:
            self._client = httpx.Client(timeout=30.0, transport=transport)
            return
        try:
            self._client = httpx.Client(timeout=30.0)
        except (httpx.InvalidURL, ValueError) as exc:
            # HTTPX Proxy reports an unsupported scheme as a ValueError.
            # Leave unrelated constructor errors (e.g. TLS settings) alone.
            if not isinstance(exc, httpx.InvalidURL) and not str(exc).startswith("Unknown scheme for proxy URL "):
                raise
            # Default construction parses environment/system proxies. Never
            # display their values or retry via a different network route.
            raise ConfigError(
                "Invalid HTTP proxy configuration. Check HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, and NO_PROXY."
            ) from None

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
        headers = {"Accept": accept}
        url = urljoin(self.base_url, path.lstrip("/"))
        repo_search = method.upper() == "GET" and path == "/search/repositories"
        if method.upper() == "GET" and (repo_search or path == "/search"):
            if repo_search:
                validate_bearer_target(url, httpx.QueryParams(merged_params).multi_items(), self.token)
            else:
                merged_params.pop("access_token", None)
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        else:
            merged_params["access_token"] = self.token
        if _requires_private_token(method, path):
            headers["private-token"] = self.token
        uncertain = " Verify the remote state before retrying this write." if method.upper() != "GET" else ""
        # Repository task-label creation alone requires a form body. Preserve
        # the public request override contract (including MCP's bearer transport).
        form_label = method.upper() == "POST" and re.fullmatch(r"/repos/[^/]+/[^/]+/labels", path) is not None
        try:
            with redacted_transport(self.token):
                if repo_search:
                    # Never merge session cookies/auth or follow a redirect, even on later pages.
                    request = httpx.Request(method, url, params=merged_params, headers=headers)
                    response = self._client.send(request, auth=None, follow_redirects=False)
                else:
                    response = self._client.request(
                        method,
                        url,
                        params=merged_params,
                        data=json if form_label else None,
                        json=None if form_label else json,
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

    def read_issue_status_page(self, endpoint: str, params: dict[str, str]) -> tuple[Any, httpx.Headers, httpx.URL]:
        """Bounded bearer-only SDK read using this client's existing HTTP transport."""
        from .repo_read import bounded_json_response  # noqa: PLC0415 - repo_read shares the canonical BASE_URL.

        route = _STATUS_ROUTE.fullmatch(endpoint)
        if self.base_url.rstrip("/") != BASE_URL.rstrip("/") or route is None:
            raise APIError("Bounded issue status requires the standard GitCode API and an issue status endpoint.")
        if (
            not isinstance(params, dict)
            or any(not isinstance(value, str) for value in params.values())
            or (not _valid_status_query(params) if route["queue"] else bool(params))
        ):
            raise APIError("Invalid query parameters for the bounded issue status endpoint.")
        return bounded_json_response(
            "Issue status", endpoint, params, self.token, (endpoint, *params, *params.values()), client=self._client
        )

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
