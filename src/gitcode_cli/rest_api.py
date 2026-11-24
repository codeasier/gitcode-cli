"""Fixed-origin, JSON-only REST transport for the generic CLI (not an MCP tool)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, unquote_plus

import httpx

from ._redact import redact, redacted_transport
from .errors import APIError, NetworkError

ORIGIN = "https://api.gitcode.com"
READ_METHODS = {"GET", "HEAD"}
MAX_BYTES = 16 * 1024 * 1024  # decoded response bytes across one invocation
MAX_PAGES = 100
_UNCERTAIN = " Verify the remote state before retrying this write."
_SAFE_HEADERS = {"accept", "if-match", "if-none-match", "if-modified-since", "if-unmodified-since"}
_SHOW_HEADERS = {"content-type", "etag", "last-modified", "retry-after", "x-ratelimit-remaining"}
_CREDENTIAL_KEYS = {
    "accesstoken",
    "refreshtoken",
    "privatetoken",
    "token",
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "password",
    "secret",
    "clientsecret",
    "apikey",
    "privatekey",
    "oauthtoken",
    "idtoken",
    "sessiontoken",
    "clientassertion",
}
_METHOD_KEYS = {"method", "methodoverride", "httpmethod", "httpmethodoverride", "xhttpmethod", "xhttpmethodoverride"}
_BAD_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
_RUNS_PATH = re.compile(r"/api/v8/repos/([^/]+)/([^/]+)/actions/runs")
_REPO_SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}")
_RUNS_FILTERS = {
    "event",
    "status",
    "branch",
    "executor",
    "pull_request_id",
    "workflow_id",
    "workflow_name",
    "startTime",
    "endTime",
}
_RUNS_BAD_PAGE = "Invalid, incomplete or changed v8 run page; no partial result was returned."
_RUNS_PARTIAL = "v8 run response explicitly indicates possible truncation; no partial result was returned."


def _control(value: str) -> bool:
    return any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unquote(value).lower())


def _check_key(key: str) -> None:
    if _key(key) in _CREDENTIAL_KEYS | _METHOD_KEYS:
        raise APIError("Invalid or reserved request field; use gc authentication, not credential fields.")


def validate_field(key: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        raise APIError("Invalid request field.")
    _check_key(key)


def _check_token(value: str, token: str) -> None:
    if token and (token in value or token in unquote_plus(value)):
        raise APIError("Refusing to send the active GitCode token outside the authorization header.")


def _check_json(value: Any, token: str) -> None:
    if isinstance(value, dict):
        for k, item in value.items():
            _check_key(k)
            _check_token(k, token)
            _check_json(item, token)
    elif isinstance(value, list):
        for item in value:
            _check_json(item, token)
    elif value is not None:
        _check_token(str(value), token)


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError("Duplicate JSON field.")
    return values


def request_body(raw: bytes | None, fields: dict[str, Any], token: str) -> bytes | None:
    if raw is None and not fields:
        return None
    if raw is not None and len(raw) > MAX_BYTES:
        raise APIError("Request body exceeds the size limit.")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_fields) if raw is not None else fields
        _check_json(data, token)
        body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
        _check_token(body.decode("ascii"), token)
    except (ValueError, UnicodeError, RecursionError):
        raise APIError("Request body must be a valid JSON document without duplicate keys.") from None
    if len(body) > MAX_BYTES:
        raise APIError("Request body exceeds the size limit.")
    return body


def safe_headers(values: tuple[str, ...], token: str) -> dict[str, str]:
    result = {"accept": "application/json"}
    for header in values:
        name, sep, value = header.partition(":")
        name = name.strip().lower()
        if not sep or name not in _SAFE_HEADERS or not value.strip() or not value.isascii() or _control(header):
            raise APIError("Invalid request header. Use Accept or an HTTP conditional header, not auth/host headers.")
        _check_token(value, token)
        result[name] = value.strip()
    return result


def _segment(raw: str) -> str:
    try:
        decoded = unquote(raw, errors="strict")
    except UnicodeError:
        raise APIError("Invalid UTF-8 in REST path.") from None
    if (
        not decoded
        or decoded in {".", ".."}
        or _BAD_ESCAPE.search(raw)
        or _control(decoded)
        or any(c in decoded for c in "/\\:?#%@;{}")
    ):
        raise APIError("Invalid REST path segment; use a relative API path without traversal or encoded separators.")
    return quote(decoded, safe="-._~")


def endpoint_url(endpoint: str, version: str | None) -> tuple[str, dict[str, str]]:
    """Build locally, never urljoin against caller-controlled strings or response links."""
    if not endpoint or endpoint.startswith("//") or "#" in endpoint or _control(endpoint):
        raise APIError("Expected a relative GitCode REST endpoint, not a URL or fragment.")
    path, _, query = endpoint.partition("?")
    parts = path.removeprefix("/").split("/")
    if parts[0] == "api":
        if len(parts) < 3 or parts[1] not in {"v5", "v8"} or version not in {None, parts[1]}:
            raise APIError("Expected /api/v5 or /api/v8 and a matching API version.")
        version, parts = parts[1], parts[2:]
    segments = [_segment(raw) for raw in parts]
    if segments[0].lower() in {"graphql", "api"} or version not in {None, "v5", "v8"}:
        raise APIError("Only GitCode REST v5 and v8 endpoints are supported.")
    try:
        if _BAD_ESCAPE.search(query):
            raise ValueError
        # Python 3.9/3.10 strict parsing can reject an entirely absent query.
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, errors="strict") if query else []
    except (ValueError, UnicodeError):
        raise APIError("Malformed REST query string.") from None
    params: dict[str, str] = {}
    for name, value in pairs:
        validate_field(name)
        if name in params or _control(value):
            raise APIError("Invalid or repeated REST query parameter.")
        params[name] = value
    return f"{ORIGIN}/api/{version or 'v5'}/{'/'.join(segments)}", params


def clean_response(value: Any, token: str) -> Any:
    if isinstance(value, dict):
        return {
            redact(k, token): "[REDACTED]" if _key(k) in _CREDENTIAL_KEYS else clean_response(v, token)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [clean_response(v, token) for v in value]
    return redact(value, token) if isinstance(value, str) else value


@dataclass
class Page:
    status: int
    headers: dict[str, str]
    data: Any
    has_body: bool


@dataclass
class _RunsPagination:
    size: int
    total: int | None = None
    ids: set[str] = field(default_factory=set)

    def check_headers(self, headers: httpx.Headers) -> None:
        if "content-range" in headers or "link" in headers:
            raise APIError(
                "Unsupported v8 run continuation or partial-response headers; no partial result was returned."
            )
        # Defensive signals, not required fields of the published v8 contract.
        for key in ("x-truncated", "x-incomplete-results"):
            if key in headers and headers[key].strip().lower() not in {"false", "0"}:
                raise APIError(_RUNS_PARTIAL)
        self._expect_headers(headers, {"x-page": self._number(), "x-per-page": self.size})

    def _number(self) -> int:
        return len(self.ids) // self.size + 1

    @staticmethod
    def _expect_headers(headers: httpx.Headers, expected: dict[str, str | int]) -> None:
        if any(headers.get(key, str(value)) != str(value) for key, value in expected.items()):
            raise APIError("Contradictory v8 run pagination headers; no partial result was returned.")

    def accept(self, data: Any, headers: httpx.Headers) -> None:
        if not isinstance(data, dict):
            raise APIError(_RUNS_BAD_PAGE)
        for key in ("truncated", "incomplete_results"):
            if key in data and not (data[key] is False or (type(data[key]) is int and data[key] == 0)):
                raise APIError(_RUNS_PARTIAL)
        total, rows = data.get("total_count"), data.get("workflow_runs")
        if type(total) is not int or total < 0 or (self.total is not None and self.total != total):
            raise APIError(_RUNS_BAD_PAGE)
        if total > self.size * MAX_PAGES:
            raise APIError("v8 run pagination limit reached; no partial result was returned.")
        if not isinstance(rows, list) or len(rows) != min(self.size, total - len(self.ids)):
            raise APIError(_RUNS_BAD_PAGE)
        number = self._number()
        page_count = (total + self.size - 1) // self.size
        next_page = number + 1 if number < page_count else None
        prev_page = number - 1 if number > 1 else None
        self._expect_headers(
            headers,
            {
                "x-total": total,
                "x-total-pages": page_count,
                "x-next-page": next_page if next_page is not None else "",
                "x-prev-page": prev_page if prev_page is not None else "",
            },
        )
        for key, value in {
            "page": number,
            "per_page": self.size,
            "total_pages": page_count,
            "next_page": next_page,
            "prev_page": prev_page,
        }.items():
            if key in data and (type(data[key]) is not type(value) or data[key] != value):
                raise APIError(_RUNS_BAD_PAGE)
        for item in rows:
            run_id = item.get("workflow_run_id") if isinstance(item, dict) else None
            if (
                not isinstance(run_id, str)
                or not 1 <= len(run_id) <= 256
                or not run_id.isprintable()
                or run_id != run_id.strip()
                or run_id in self.ids
            ):
                raise APIError(_RUNS_BAD_PAGE)
            self.ids.add(run_id)
        self.total = total

    def complete(self) -> bool:
        return len(self.ids) == self.total


def is_v8_runs_pagination_endpoint(raw: str, version: str | None) -> bool:
    """Recognize this route without obtaining an origin or using request-supplied scope."""
    path = raw.partition("?")[0].replace("{owner}", "owner").replace("{repo}", "repo")
    try:
        url, _ = endpoint_url(path, version)
    except APIError:
        # The common request validator still decides whether other paths are usable.
        return False
    return _RUNS_PATH.fullmatch(url.removeprefix(ORIGIN)) is not None


def _runs_pagination(
    url: str, params: dict[str, str], headers: dict[str, str], repo_scope: tuple[str, str] | None
) -> _RunsPagination | None:
    route = _RUNS_PATH.fullmatch(url.removeprefix(ORIGIN))
    if route is None:
        return None
    target = route.group(1), route.group(2)
    if not all(_REPO_SLUG.fullmatch(part) for part in target) or (repo_scope is not None and target != repo_scope):
        raise APIError("v8 run pagination requires an exact repository matching the chosen scope.")
    if set(headers) != {"accept"} or headers["accept"].lower() != "application/json":
        raise APIError("v8 run pagination requires JSON and does not accept conditional headers.")
    if params.keys() - _RUNS_FILTERS - {"page", "per_page"}:
        raise APIError("Use only documented v8 run query parameters when paginating.")
    if params.get("page", "1") != "1":
        raise APIError("v8 run pagination must start at page 1.")
    raw_size = params.get("per_page", "20")
    if not re.fullmatch(r"[1-9][0-9]?|100", raw_size):
        raise APIError("v8 run pagination requires per_page from 1 through 100.")
    if any(not params[key].strip() or len(params[key]) > 1024 for key in _RUNS_FILTERS & params.keys()):
        raise APIError("v8 run pagination requires nonblank, bounded filter values.")
    params["per_page"] = raw_size
    headers["accept"] = "application/json"
    headers["accept-encoding"] = "identity"
    return _RunsPagination(int(raw_size))


def _finite_json_number(raw: str) -> float:
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number.")
    return number


def _checked_size(response: httpx.Response, remaining: int, uncertain: str) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes(64 * 1024):
        if len(body) + len(chunk) > remaining:
            raise APIError("REST response size limit exceeded." + uncertain)
        body.extend(chunk)
    return bytes(body)


def _confirmed_status(status: int, method: str) -> bool:
    if method == "DELETE":
        return status in {200, 204}
    if method not in READ_METHODS:
        return status in {200, 201, 204, 205}
    return True


def _read(
    response: httpx.Response, method: str, token: str, remaining: int, *, runs: _RunsPagination | None = None
) -> tuple[Page, int, bytes]:
    status = response.status_code
    if runs is not None:
        if status != 200:
            raise APIError(f"GitCode v8 runs returned HTTP {status}; no partial result was returned.", status)
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise APIError("Compressed v8 run pages are refused; no partial result was returned.")
        runs.check_headers(response.headers)
    uncertain = "" if method in READ_METHODS else _UNCERTAIN
    if status == 202:
        raise APIError("HTTP 202: request accepted; completion is not confirmed." + uncertain, status)
    if not (200 <= status < 300 or (status == 304 and method in READ_METHODS)):
        raise APIError(f"GitCode API returned HTTP {status}; redirects and retries are disabled." + uncertain, status)
    if not _confirmed_status(status, method):
        raise APIError(f"HTTP {status}: unconfirmed write result." + uncertain, status)
    headers = {k: redact(v, token) for k, v in response.headers.items() if k in _SHOW_HEADERS and not _control(v)}
    if method == "HEAD" or status in {204, 205, 304}:
        return Page(status, headers, None, False), 0, b""
    raw = _checked_size(response, remaining, uncertain)
    try:
        if runs is not None:
            data = json.loads(
                raw,
                object_pairs_hook=_unique_fields,
                parse_float=_finite_json_number,
                parse_constant=_finite_json_number,
            )
            # Validate identities and totals before redacting. Do not retain raw pages or
            # make assumptions based on aliases in the displayed (redacted) output.
            runs.accept(data, response.headers)
            digest = b""
        else:
            data = json.loads(raw)
            if uncertain and data is None:
                raise ValueError
            digest = hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).digest()
        clean = clean_response(data, token)
    except (ValueError, UnicodeError, RecursionError):
        raise APIError("Expected a valid JSON response from GitCode." + uncertain, status) from None
    return Page(status, headers, clean, True), len(raw), digest


def open_client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=False, trust_env=False)


def _page_number(params: dict[str, str]) -> int:
    raw = params.get("page", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,8}", raw):
        raise APIError("Pagination requires a positive integer page.")
    return int(raw)


def validate_bearer_target(url: str, query: Iterable[tuple[str, str]], token: str) -> None:
    """Validate the actual URL fields before sending credentials in a header."""
    if token and (not token.isascii() or not token.isprintable() or any(c.isspace() for c in token)):
        raise APIError("Invalid GitCode authentication token.")
    _check_token(url, token)
    for key, value in query:
        validate_field(key)
        if _control(value):
            raise APIError("Invalid request query value.")
        _check_token(key, token)
        _check_token(value, token)


def _request_target(
    endpoint: str,
    version: str | None,
    query: dict[str, str],
    token: str,
) -> tuple[str, dict[str, str]]:
    url, params = endpoint_url(endpoint, version)
    if params.keys() & query.keys():
        raise APIError("A query parameter was supplied twice.")
    params.update(query)
    validate_bearer_target(url, params.items(), token)
    return url, params


def _array_pagination_done(page: Page, digest: bytes, seen: set[bytes]) -> bool:
    if not isinstance(page.data, list):
        raise APIError("Pagination requires a JSON array response; no partial result was returned.")
    if not page.data:
        return True
    if digest in seen:
        raise APIError("Repeated REST page; no partial result was returned.")
    seen.add(digest)
    return False


def _prepare_page(url: str, params: dict[str, str], number: int, paginate: bool, strict_runs: bool, token: str) -> None:
    if paginate:
        params["page"] = str(number)
    if strict_runs:
        # Common preflight runs before generation of page/per_page. Check the
        # fully serialized URL and its decoded equivalent immediately before sending.
        _check_token(str(httpx.URL(url, params=params)), token)


def fetch(
    endpoint: str,
    version: str | None,
    method: str,
    token: str,
    headers: tuple[str, ...],
    query: dict[str, str],
    body: bytes | None,
    paginate: bool,
    *,
    repo_scope: tuple[str, str] | None = None,
) -> list[Page]:
    url, params = _request_target(endpoint, version, query, token)
    if method not in READ_METHODS | {"POST", "PUT", "PATCH", "DELETE"} or (paginate and method != "GET"):
        raise APIError("Invalid HTTP method for this REST request.")
    if not token and method not in READ_METHODS:
        raise APIError("Authenticate with gc before issuing a write request.")
    request_headers = safe_headers(headers, token)
    runs = _runs_pagination(url, params, request_headers, repo_scope) if paginate else None
    if runs is not None and body is not None:
        raise APIError("v8 run pagination is a read-only GET and does not accept a body.")
    if token:
        request_headers["authorization"] = f"Bearer {token}"
    if body is not None:
        request_headers["content-type"] = "application/json"
    number = _page_number(params) if paginate else 1
    pages: list[Page] = []
    seen: set[bytes] = set()
    remaining = MAX_BYTES
    try:
        with open_client() as client, redacted_transport(token):
            for offset in range(MAX_PAGES):
                _prepare_page(url, params, number + offset, paginate, runs is not None, token)
                client.cookies.clear()
                with client.stream(
                    method, url, params=params, headers=request_headers, content=body, follow_redirects=False
                ) as response:
                    page, used, digest = _read(response, method, token, remaining, runs=runs)
                remaining -= used
                if not paginate:
                    return [page]
                if runs is not None:
                    pages.append(page)
                    if runs.complete():
                        return pages
                    continue
                if _array_pagination_done(page, digest, seen):
                    return pages or [page]
                pages.append(page)
    except httpx.HTTPError:
        raise NetworkError("GitCode API transport failed." + ("" if method in READ_METHODS else _UNCERTAIN)) from None
    raise APIError("REST pagination limit reached; no partial result was returned.")
