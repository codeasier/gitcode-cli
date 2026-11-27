"""Bounded, credential-safe HTTP adapter for pygitcode's service layer."""

from __future__ import annotations

import json as json_module
import math
import re
from contextlib import closing
from typing import Any, Literal
from urllib.parse import quote, unquote

import anyio
import httpx
from gitcode_cli.client import GitCodeClient
from gitcode_cli.services.files import FileService
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.pulls import PullRequestService
from gitcode_cli.services.repos import RepoService

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


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _finite_page_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def _reject_page_constant(_: str) -> Any:
    raise ValueError("nonstandard JSON constant")


def _require_utf8_scalars(value: Any) -> None:
    # The JSON decoder combines escaped surrogate pairs but accepts lone ones.
    # Verify every string (including nested names) before MCP encodes its result.
    if isinstance(value, str):
        value.encode()
    elif isinstance(value, list):
        for item in value:
            _require_utf8_scalars(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            key.encode()
            _require_utf8_scalars(item)


def _page_length(headers: httpx.Headers, limit: int) -> int | None:
    # Bound metadata before inspecting pagination links or consuming body bytes.
    fields = headers.raw
    if len(fields) > 128 or sum(len(k) + len(v) + 4 for k, v in fields) > 32_768:
        raise GitCodeError("response_too_large", "GitCode page headers exceed the size limit.")
    types = headers.get_list("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise GitCodeError("invalid_response", "GitCode did not return a JSON page.")
    length = headers.get("content-length")
    if length is None:
        return None
    if not (1 <= len(length) <= 19 and length.isascii() and length.isdigit()):
        raise GitCodeError("invalid_response", "GitCode returned an invalid page length.")
    if int(length) > limit:
        raise GitCodeError(
            "response_too_large", "The label catalog exceeds the configured size limit."
        )
    return int(length)


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
        self.label_timeout = min(30.0, timeout)
        self._transport = transport
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
        self.files = FileService(self)
        self.repos = RepoService(self)

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

    def _decode_label_page(self, content: bytearray) -> Any:
        try:
            value = json_module.loads(
                content.decode(),
                object_pairs_hook=unique_object,
                parse_constant=_reject_page_constant,
                parse_float=_finite_page_float,
            )
            _require_utf8_scalars(value)
            return self._redact(value)
        except (ValueError, RecursionError):
            raise GitCodeError(
                "invalid_response", "GitCode returned an invalid JSON page."
            ) from None

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
        _strict_identity_json: bool = False,
        _page_budget: int | None = None,
    ) -> Any:
        """Issue a bounded request using pygitcode's public request signature."""
        result = self._bounded_request(
            method,
            path,
            params=params,
            json=json,
            accept=accept,
            response_format=response_format,
            _strict_identity_json=_strict_identity_json,
            _page_budget=_page_budget,
        )
        return result if _page_budget is not None else result[0]

    def label_scan_client(self) -> httpx.AsyncClient:
        """One independently cancellable client per read-only catalog scan."""
        if self._transport is not None and not isinstance(
            self._transport, httpx.AsyncBaseTransport
        ):
            raise GitCodeError("invalid_configuration", "Label scan requires an async transport.")
        return httpx.AsyncClient(
            timeout=self.label_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=self._transport,
        )

    async def read_label_page(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        page: int,
        per_page: int,
        remaining: int,
    ) -> tuple[Any, httpx.Headers, int]:
        """A fixed Bearer GET; no sync worker or provider-chosen targets."""
        if not self.token:
            raise GitCodeError(
                "configuration_error", "Set GITCODE_TOKEN or GC_TOKEN before calling GitCode tools."
            )
        if (
            not re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/labels", path)
            or any(part in {".", ".."} for part in path.split("/"))
            or self.token in path
        ):
            raise GitCodeError("invalid_path", "Only validated GitCode label paths are allowed.")
        if remaining < 1:
            raise GitCodeError(
                "response_too_large", "The label catalog exceeds the configured size limit."
            )
        # A standalone request bypasses the client's retained response cookies.
        outbound = httpx.Request(
            "GET",
            API_BASE_URL + path.lstrip("/"),
            params={"page": page, "per_page": per_page},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "codeasier-gitcode-mcp",
            },
        )
        try:
            response = await client.send(outbound, stream=True, auth=None, follow_redirects=False)
            try:
                status = response.status_code
                if 300 <= status < 400:
                    raise GitCodeError(
                        "upstream_redirect",
                        "GitCode returned a redirect; credentials were not forwarded.",
                        status_code=status,
                    )
                if status >= 400:
                    raise self._status_error(response)
                if (
                    status != 200
                    or response.headers.get("Content-Encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise GitCodeError(
                        "invalid_response", "GitCode returned an invalid page response."
                    )
                length = _page_length(response.headers, remaining)
                content = bytearray()
                if response.is_stream_consumed:
                    content.extend(response.content)
                else:
                    async for chunk in response.aiter_raw():
                        if len(chunk) > remaining - len(content):
                            raise GitCodeError(
                                "response_too_large",
                                "The label catalog exceeds the configured size limit.",
                            )
                        content.extend(chunk)
                        await anyio.lowlevel.checkpoint()
                if len(content) > remaining:
                    raise GitCodeError(
                        "response_too_large", "The label catalog exceeds the configured size limit."
                    )
                if not content or (length is not None and length != len(content)):
                    raise GitCodeError(
                        "invalid_response", "GitCode returned an incomplete JSON page."
                    )
                return self._decode_label_page(content), response.headers, len(content)
            finally:
                await response.aclose()
        except httpx.TimeoutException:
            raise GitCodeError("timeout", "GitCode did not respond in time.") from None
        except httpx.HTTPError:
            raise GitCodeError("network_error", "The GitCode request failed.") from None
        except (ValueError, RecursionError):
            raise GitCodeError(
                "invalid_response", "GitCode returned an invalid JSON page."
            ) from None

    def task_label_request(
        self,
        method: Literal["GET", "POST", "PATCH", "DELETE"],
        path: str,
        *,
        params: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> tuple[Any, httpx.Headers]:
        """Task-label wire contracts: POST form only, PATCH query, synchronous receipts."""
        collection = re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/labels", path)
        member = re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/labels/[^/]+", path)
        if not (
            (
                method == "GET"
                and collection
                and form is None
                and set(params or {}) == {"page", "per_page"}
            )
            or (
                method == "POST"
                and collection
                and params is None
                and set(form or {}) == {"name", "color"}
            )
            or (
                method == "PATCH"
                and member
                and form is None
                and bool(params)
                and set(params) <= {"name", "color"}
            )
            or (method == "DELETE" and member and params is None and form is None)
        ):
            raise GitCodeError("invalid_arguments", "Invalid repository task-label operation.")
        result = self._bounded_request(
            method,
            path,
            params=params,
            form=form,
            statuses={200, 204}
            if method == "DELETE"
            else {200, 201}
            if method == "POST"
            else {200},
        )
        return result[0], result[1]

    def _bounded_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        accept: str = "application/json",
        response_format: Literal["json", "text"] = "json",
        statuses: set[int] | None = None,
        _strict_identity_json: bool = False,
        _page_budget: int | None = None,
    ) -> tuple[Any, httpx.Headers] | tuple[Any, httpx.Headers, int]:
        # Native label scans need strict pages, their pagination headers and a
        # cumulative byte budget. Never change default service request behavior.
        limit = self.max_response_bytes
        if _page_budget is not None:
            _strict_identity_json = True
            limit = min(limit, _page_budget)
            if limit < 1:
                raise GitCodeError(
                    "response_too_large", "The label catalog exceeds the configured size limit."
                )
        if _strict_identity_json and (
            method != "GET" or json is not None or form is not None or response_format != "json"
        ):
            raise GitCodeError("invalid_arguments", "Invalid strict GitCode request.")
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
            # Keep existing client defaults, but never forward credentials
            # implicitly learned via an earlier upstream Set-Cookie.
            body = {"data": form} if form is not None else {"json": json}
            outbound = self._client.build_request(
                method,
                url,
                params=query,
                headers={
                    "Accept": accept,
                    "Authorization": f"Bearer {self.token}",
                    "User-Agent": "codeasier-gitcode-mcp",
                    **({"Accept-Encoding": "identity"} if _strict_identity_json else {}),
                },
                **body,
            )
            outbound.headers.pop("cookie", None)
            with closing(
                self._client.send(outbound, stream=True, auth=None, follow_redirects=False)
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
                if statuses is not None and response.status_code not in statuses:
                    raise GitCodeError(
                        "invalid_response",
                        "Unexpected GitCode response status.",
                        operation_may_have_completed=True if mutation else None,
                    )
                if _strict_identity_json and (
                    response.status_code != 200
                    or response.headers.get("Content-Encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise GitCodeError(
                        "invalid_response",
                        "GitCode returned an invalid page response."
                        if _page_budget is not None
                        else "GitCode returned an invalid fork sync response.",
                    )
                expected_length = (
                    _page_length(response.headers, limit) if _page_budget is not None else None
                )
                content = bytearray()
                chunk_size = min(65_536, limit + 1)
                if _strict_identity_json:
                    # Buffered mock responses have already consumed their stream.
                    stream = (
                        (response.content,)
                        if response.is_stream_consumed
                        else response.iter_raw(chunk_size=chunk_size)
                    )
                else:
                    stream = response.iter_bytes(chunk_size=chunk_size)
                for chunk in stream:
                    content.extend(chunk)
                    if len(content) > limit:
                        if _page_budget is not None:
                            raise GitCodeError(
                                "response_too_large",
                                "The label catalog exceeds the configured size limit.",
                            )
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
        if _page_budget is not None:
            if not content or (expected_length is not None and expected_length != len(content)):
                raise GitCodeError("invalid_response", "GitCode returned an incomplete JSON page.")
            return self._decode_label_page(content), response.headers, len(content)
        if not content:
            # Task-label DELETE can return either an empty 200 or a 204.
            # Its caller still requires an independent catalog readback.
            if statuses is not None and method != "DELETE":
                raise GitCodeError(
                    "invalid_response",
                    "Expected a task-label response body.",
                    operation_may_have_completed=True if mutation else None,
                )
            return None, response.headers
        try:
            if response_format == "text":
                return self._redact(content.decode("utf-8")), response.headers
            if _strict_identity_json:
                parsed = json_module.loads(content, object_pairs_hook=unique_object)
            else:
                parsed = json_module.loads(content)
            if statuses is not None and parsed is None:
                raise GitCodeError(
                    "invalid_response",
                    "Invalid null task-label response.",
                    operation_may_have_completed=True if mutation else None,
                )
            return self._redact(parsed), response.headers
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
