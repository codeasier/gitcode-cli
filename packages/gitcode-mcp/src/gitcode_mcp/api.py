"""Bounded, credential-safe HTTP adapter for pygitcode's service layer."""

from __future__ import annotations

import json as json_module
from typing import Any, Literal
from urllib.parse import quote, unquote

import httpx
from gitcode_cli.client import GitCodeClient
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.pulls import PullRequestService

API_BASE_URL = "https://api.gitcode.com/api/v5/"


class GitCodeError(Exception):
    """An error safe to return to an MCP caller without upstream response text."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
        operation_may_have_completed: bool | None = None,
    ) -> None:
        if operation_may_have_completed:
            message += (
                " The write may have completed. Verify remote state before retrying;"
                " do not automatically retry this operation."
            )
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        self.operation_may_have_completed = operation_may_have_completed

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.operation_may_have_completed is not None:
            result["operation_may_have_completed"] = self.operation_may_have_completed
        return result


def segment(value: str) -> str:
    """Encode a validated resource name as exactly one URL path segment."""
    return quote(value, safe="")


class GitCodeAPI(GitCodeClient):
    """Reuse pygitcode services, replacing its query-token HTTP implementation.

    This client has one fixed upstream host. Redirects and environment proxies
    are disabled; no upstream error body, URL, or exception text reaches tools.
    Requests are never retried automatically, particularly after a write.
    ``transport`` is an in-process test seam, not a configurable upstream URL.
    """

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        max_response_bytes: int = 2_000_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if token and any(character.isspace() for character in token):
            raise GitCodeError(
                "invalid_configuration", "The GitCode token cannot contain whitespace."
            )
        if timeout <= 0 or max_response_bytes < 1:
            raise GitCodeError("invalid_configuration", "HTTP limits must be positive.")
        # Do not call the upstream constructor, which creates a second client.
        self.token = token
        self.base_url = API_BASE_URL
        self.max_response_bytes = max_response_bytes
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={
                "User-Agent": "codeasier-gitcode-mcp",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        self.issues = IssueService(self)
        self.pulls = PullRequestService(self)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitCodeAPI:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _redact(self, value: Any) -> Any:
        if not self.token:
            return value
        if isinstance(value, str):
            return value.replace(self.token, "[REDACTED]")
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, dict):
            return {self._redact(key): self._redact(item) for key, item in value.items()}
        return value

    @staticmethod
    def _status_error(response: httpx.Response, *, mutation: bool = False) -> GitCodeError:
        status = response.status_code
        errors = {
            401: ("authentication_failed", "GitCode rejected the configured credential."),
            403: ("permission_denied", "The GitCode credential cannot perform this operation."),
            404: ("not_found", "The GitCode resource was not found or is not accessible."),
            409: (
                "conflict",
                "GitCode reported a conflict; read the current resource before retrying.",
            ),
            422: (
                "upstream_validation",
                "GitCode rejected the operation's parameters or current state.",
            ),
            429: (
                "rate_limited",
                "GitCode's rate limit was reached; retry after the indicated delay.",
            ),
        }
        code, message = errors.get(
            status, ("upstream_error", "GitCode returned an unsuccessful response.")
        )
        retry_after = None
        header = response.headers.get("Retry-After", "")
        if status == 429 and header.isascii() and header.isdigit() and len(header) <= 6:
            retry_after = min(int(header), 86400)
        return GitCodeError(
            code,
            message,
            status_code=status,
            retry_after=retry_after,
            operation_may_have_completed=True if mutation and 500 <= status < 600 else None,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        response_format: Literal["json", "text"] = "json",
    ) -> Any:
        """Issue a bounded request using pygitcode's public request signature."""
        mutation = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        if not self.token:
            raise GitCodeError(
                "configuration_error", "Set GITCODE_TOKEN or GC_TOKEN before calling GitCode tools."
            )
        decoded = unquote(path)
        if (
            not path.startswith("/repos/")
            or any(part in {".", ".."} for part in decoded.split("/"))
            or any(character in decoded for character in "\\?#\r\n")
            or "://" in decoded
        ):
            raise GitCodeError(
                "invalid_path", "Only validated GitCode repository API paths are allowed."
            )
        if params and any(
            key.casefold() in {"access_token", "token", "authorization"} for key in params
        ):
            raise GitCodeError(
                "invalid_arguments", "Credentials cannot be supplied in API query parameters."
            )
        url = API_BASE_URL + path.lstrip("/")
        query = {key: value for key, value in (params or {}).items() if value is not None}
        try:
            with self._client.stream(
                method, url, params=query, json=json, headers={"Accept": accept}
            ) as response:
                if 300 <= response.status_code < 400:
                    raise GitCodeError(
                        "upstream_redirect",
                        "GitCode returned a redirect; credentials were not forwarded.",
                        status_code=response.status_code,
                        operation_may_have_completed=True if mutation else None,
                    )
                if response.status_code >= 400:
                    raise self._status_error(response, mutation=mutation)
                content = bytearray()
                for chunk in response.iter_bytes(
                    chunk_size=min(65_536, self.max_response_bytes + 1)
                ):
                    content.extend(chunk)
                    if len(content) > self.max_response_bytes:
                        raise GitCodeError(
                            "response_too_large",
                            (
                                "GitCode's write response exceeds the configured size limit."
                                if mutation
                                else "GitCode's response exceeds the configured size limit; request a smaller page or file. For unpaged PR data, use git diff in a local checkout."
                            ),
                            operation_may_have_completed=True if mutation else None,
                        )
        except httpx.TimeoutException:
            raise GitCodeError(
                "timeout",
                "GitCode did not respond in time.",
                operation_may_have_completed=True if mutation else None,
            ) from None
        except httpx.HTTPError:
            raise GitCodeError(
                "network_error",
                "The GitCode request failed.",
                operation_may_have_completed=True if mutation else None,
            ) from None
        if not content:
            return None
        try:
            if response_format == "text":
                return self._redact(content.decode("utf-8"))
            return self._redact(json_module.loads(content))
        except (ValueError, UnicodeError):
            raise GitCodeError(
                "invalid_response",
                "GitCode returned an invalid response format.",
                operation_may_have_completed=True if mutation else None,
            ) from None

    def page(self, path: str, *, page: int, per_page: int, **params: Any) -> dict[str, Any]:
        """Fetch exactly one page. A full page conservatively offers a next page."""
        items = self.get(path, params={**params, "page": page, "per_page": per_page})
        return self.page_result(items, page=page, per_page=per_page)

    @staticmethod
    def page_result(items: Any, *, page: int, per_page: int) -> dict[str, Any]:
        if not isinstance(items, list):
            raise GitCodeError("invalid_response", "GitCode did not return the expected list.")
        if len(items) > per_page:
            raise GitCodeError(
                "invalid_response", "GitCode returned more items than the requested page size."
            )
        return {
            "data": items,
            "page": page,
            "per_page": per_page,
            "next_page": page + 1 if len(items) == per_page else None,
            "pagination_mode": "upstream",
            "pagination_note": "A full page may have a next page; that next page can be empty.",
        }

    @staticmethod
    def collection_page_result(items: Any, *, page: int, per_page: int) -> dict[str, Any]:
        """Slice a bounded response from an endpoint without documented paging.

        This does not call pygitcode's eager pagination or assume the upstream
        accepts page/per_page. Every tool invocation fetches the collection
        again; a changing resource is not a stable multi-page snapshot.
        """
        if not isinstance(items, list):
            raise GitCodeError("invalid_response", "GitCode did not return the expected list.")
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "data": items[start:end],
            "page": page,
            "per_page": per_page,
            "next_page": page + 1 if end < len(items) else None,
            "pagination_mode": "client",
            "total_items": len(items),
            "pagination_note": "GitCode does not document upstream pagination for this endpoint. One size-bounded response is sliced locally; each call fetches it again, so pages are not a stable snapshot.",
        }
