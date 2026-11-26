#!/usr/bin/env python3
"""Expose GitCode merge requests through a local Gitea-compatible API for Orca.

Orca has no native GitCode provider. Its Gitea provider accepts a self-hosted
API base URL, so this adapter translates the small Gitea surface Orca reads
(pull requests and commit status) into GitCode REST v5 calls.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

GITCODE_API_BASE = "https://api.gitcode.com/api/v5"
GITCODE_WEB_BASE = "https://gitcode.com"
DEFAULT_CACHE_TTL = 15.0
DEFAULT_TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CACHE_ENTRIES = 512

SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
REPO_ROUTE = r"^/repos/([^/]+)/([^/]+)"
LIST_RE = re.compile(REPO_ROUTE + r"/pulls/?$")
DETAIL_RE = re.compile(REPO_ROUTE + r"/pulls/([^/]+)/?$")
STATUS_RE = re.compile(REPO_ROUTE + r"/commits/([^/]+)/status/?$")

FetchJson = Callable[[str, dict[str, str]], Any]


def _log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


class BadRequestError(Exception):
    pass


class UpstreamError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class LinkerConfig:
    token: str
    api_base: str = GITCODE_API_BASE
    cache_ttl: float = DEFAULT_CACHE_TTL
    fork_pr_source: str = "both"
    fetch: FetchJson | None = None

    def __post_init__(self) -> None:
        if self.fetch is None:
            self.fetch = make_gitcode_fetch(self.api_base, self.token)


class TtlCache:
    def __init__(self, ttl: float):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            return entry[1] if entry is not None and entry[0] > time.monotonic() else None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl, value)
            if len(self._entries) > MAX_CACHE_ENTRIES:
                self._entries = {k: v for k, v in self._entries.items() if v[0] > time.monotonic()}

    def get_or_load(self, key: str, loader: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > now:
                return entry[1]
            if len(self._entries) > MAX_CACHE_ENTRIES:
                self._entries = {k: v for k, v in self._entries.items() if v[0] > now}
        value = loader()
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl, value)
        return value


def _read_limited(stream: Any) -> bytes:
    body = stream.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise UpstreamError(502, "GitCode response exceeded the size limit")
    return body


def gitcode_request(api_base: str, token: str, path: str, params: dict[str, str], timeout: float) -> Any:
    query = {key: value for key, value in params.items() if value is not None}
    if token:
        query["access_token"] = token
    url = f"{api_base.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "orca-gitcode-linker/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            body = _read_limited(response)
    except HTTPError as error:
        with contextlib.suppress(Exception):
            _read_limited(error)
        if error.code == 404:
            raise UpstreamError(404, "GitCode resource not found") from None
        if error.code in (401, 403):
            raise UpstreamError(502, "GitCode authentication failed; run gc auth login") from None
        if error.code == 429:
            raise UpstreamError(429, "GitCode rate limit reached") from None
        raise UpstreamError(502, f"GitCode HTTP {error.code}") from None
    except URLError:
        raise UpstreamError(502, "GitCode network error") from None
    except OSError:
        raise UpstreamError(502, "GitCode request failed") from None
    try:
        return json.loads(body)
    except (UnicodeError, ValueError):
        raise UpstreamError(502, "GitCode returned invalid JSON") from None


def make_gitcode_fetch(api_base: str, token: str, timeout: float = DEFAULT_TIMEOUT) -> FetchJson:
    def fetch(path: str, params: dict[str, str]) -> Any:
        return gitcode_request(api_base, token, path, params, timeout)

    return fetch


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _pull_web_url(owner: str, repo: str, raw: dict[str, Any], number: int) -> str:
    url = _text(raw.get("html_url"))
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return f"{GITCODE_WEB_BASE}/{quote(owner, safe='')}/{quote(repo, safe='')}/pulls/{number}"


def map_pull(owner: str, repo: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    number = raw.get("number")
    title = _text(raw.get("title"))
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0 or not title:
        return None
    raw_state = _text(raw.get("state")).lower()
    merged = raw_state == "merged" or bool(_text(raw.get("merged_at")))
    state = "open" if raw_state == "open" else "closed"
    head_raw = raw.get("head") if isinstance(raw.get("head"), dict) else {}
    base_raw = raw.get("base") if isinstance(raw.get("base"), dict) else {}
    head_ref = _text(head_raw.get("ref"))
    head_label = _text(head_raw.get("label")) or head_ref
    head_sha = _text(head_raw.get("sha"))
    mapped: dict[str, Any] = {
        "number": number,
        "title": title,
        "html_url": _pull_web_url(owner, repo, raw, number),
        "state": state,
        "merged": merged,
        "draft": bool(raw.get("draft")),
        "updated_at": _text(raw.get("updated_at")) or _text(raw.get("created_at")),
        "head": {"ref": head_ref, "label": head_label, "sha": head_sha},
        "base": {"ref": _text(base_raw.get("ref"))},
    }
    if isinstance(raw.get("mergeable"), bool):
        mapped["mergeable"] = raw["mergeable"]
    return mapped


def _updated_sort_key(pull: dict[str, Any]) -> float:
    value = pull.get("updated_at")
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _matches_state(pull: dict[str, Any], state: str) -> bool:
    if state == "open":
        return pull.get("state") == "open"
    if state == "closed":
        return pull.get("state") == "closed"
    if state == "merged":
        return pull.get("merged") is True
    return True


def _segment(value: str, label: str) -> str:
    decoded = unquote(value)
    if not SEGMENT_RE.fullmatch(decoded):
        raise BadRequestError(f"Invalid {label}.")
    return decoded


def _number(value: str) -> int:
    decoded = unquote(value)
    if not decoded.isdigit() or int(decoded) <= 0:
        raise BadRequestError("Invalid pull request number.")
    return int(decoded)


def _int_query(query: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
    values = query.get(name)
    if not values:
        return default
    if len(values) != 1:
        raise BadRequestError(f"Invalid {name}.")
    try:
        value = int(values[0])
    except ValueError:
        raise BadRequestError(f"Invalid {name}.") from None
    if value < minimum or value > maximum:
        raise BadRequestError(f"Invalid {name}.")
    return value


def _state_query(query: dict[str, list[str]]) -> str:
    values = query.get("state")
    if not values:
        return "all"
    if len(values) != 1 or values[0] not in {"all", "open", "closed", "merged"}:
        raise BadRequestError("Invalid state.")
    return values[0]


def _split_slug(slug: str) -> tuple[str, str] | None:
    parts = slug.split("/", 1)
    if len(parts) != 2 or not SEGMENT_RE.fullmatch(parts[0]) or not SEGMENT_RE.fullmatch(parts[1]):
        return None
    return parts[0], parts[1]


def _parent_slug(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    candidate = raw.get("parentfull_name")
    if not isinstance(candidate, str) or not candidate.strip():
        parent = raw.get("parent")
        candidate = parent.get("full_name") if isinstance(parent, dict) else None
    if not isinstance(candidate, str):
        return None
    candidate = candidate.strip()
    return candidate if _split_slug(candidate) else None


def load_parent_slug(config: LinkerConfig, meta_cache: TtlCache, owner: str, repo: str) -> str | None:
    key = f"meta:{owner}/{repo}"

    def load() -> str | None:
        return _parent_slug(config.fetch(f"/repos/{owner}/{repo}", {}))

    return meta_cache.get_or_load(key, load)


def pr_sources(config: LinkerConfig, meta_cache: TtlCache, owner: str, repo: str) -> list[str]:
    origin = f"{owner}/{repo}"
    if config.fork_pr_source == "origin":
        return [origin]
    sources = [origin]
    seen = {origin.lower()}
    current = (owner, repo)
    for _ in range(3):
        try:
            parent = load_parent_slug(config, meta_cache, *current)
        except UpstreamError as error:
            _log(f"cannot read fork parent for {current[0]}/{current[1]}: {error.message}")
            break
        if not parent or parent.lower() in seen:
            break
        sources.append(parent)
        seen.add(parent.lower())
        split = _split_slug(parent)
        if split is None:
            break
        current = split
    if config.fork_pr_source == "parent" and len(sources) > 1:
        return [sources[-1]]
    return sources


def load_pulls(
    config: LinkerConfig,
    cache: TtlCache,
    meta_cache: TtlCache,
    source_map: TtlCache,
    owner: str,
    repo: str,
    state: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    sources = pr_sources(config, meta_cache, owner, repo)
    key = f"pulls:{','.join(sources)}:{state}:{page}:{limit}"
    api_state = "open" if state == "open" else "all"

    def load() -> list[dict[str, Any]]:
        params = {"state": api_state, "page": str(page), "per_page": str(limit)}

        def fetch(source: str) -> Any:
            split = _split_slug(source)
            if split is None:
                return None
            source_owner, source_repo = split
            return config.fetch(f"/repos/{source_owner}/{source_repo}/pulls", params)

        results: list[Any] = []
        with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
            futures = [pool.submit(fetch, source) for source in sources]
            for index, future in enumerate(futures):
                try:
                    results.append(future.result())
                except UpstreamError as error:
                    if index == 0:
                        raise
                    _log(f"skipping PR source {sources[index]}: {error.message}")
                    results.append(None)
        pulls: list[dict[str, Any]] = []
        for source, data in zip(sources, results):
            split = _split_slug(source)
            if split is None:
                continue
            source_owner, source_repo = split
            if not isinstance(data, list):
                if source == sources[0]:
                    raise UpstreamError(502, "GitCode returned an invalid pull request list")
                continue
            for raw in data:
                mapped = map_pull(source_owner, source_repo, raw)
                if mapped is None:
                    continue
                source_map.set(f"{owner}/{repo}:{mapped['number']}", source)
                if _matches_state(mapped, state):
                    pulls.append(mapped)
        pulls.sort(key=_updated_sort_key, reverse=True)
        return pulls

    return cache.get_or_load(key, load)


def load_pull(
    config: LinkerConfig,
    cache: TtlCache,
    meta_cache: TtlCache,
    source_map: TtlCache,
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    sources = pr_sources(config, meta_cache, owner, repo)
    map_key = f"{owner}/{repo}:{number}"
    cached_source = source_map.get(map_key)
    ordered = [cached_source] if cached_source in sources else []
    ordered.extend(source for source in sources if source not in ordered)
    key = f"pull:{','.join(ordered)}:{number}"

    def load() -> dict[str, Any]:
        last_error: UpstreamError | None = None
        for source in ordered:
            split = _split_slug(source)
            if split is None:
                continue
            source_owner, source_repo = split
            try:
                raw = config.fetch(f"/repos/{source_owner}/{source_repo}/pulls/{number}", {})
            except UpstreamError as error:
                if error.status == 404:
                    continue
                last_error = error
                continue
            mapped = map_pull(source_owner, source_repo, raw)
            if mapped is None:
                last_error = UpstreamError(502, "GitCode returned an invalid pull request")
                continue
            source_map.set(map_key, source)
            return mapped
        raise last_error or UpstreamError(404, "GitCode pull request not found")

    return cache.get_or_load(key, load)


def neutral_commit_status(sha: str) -> dict[str, Any]:
    return {"state": "", "statuses": [], "sha": sha, "total_count": 0}


class LinkerHandler(BaseHTTPRequestHandler):
    server: LinkerServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        started = time.monotonic()
        try:
            status, payload = self._dispatch()
        except BadRequestError as error:
            status, payload = 400, {"message": str(error)}
        except UpstreamError as error:
            status, payload = error.status, {"message": error.message}
        except Exception:
            _log(f"internal error for {urlsplit(self.path).path}")
            status, payload = 500, {"message": "Internal adapter error"}
        self._send(status, payload)
        elapsed = (time.monotonic() - started) * 1000
        _log(f"{self.command} {urlsplit(self.path).path} -> {status} ({elapsed:.0f} ms)")

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _dispatch(self) -> tuple[int, dict[str, Any]]:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith("/api/v1/"):
            path = path[len("/api/v1") :]
        elif path == "/api/v1":
            path = "/"
        query = parse_qs(parsed.query, keep_blank_values=True)
        config = self.server.config
        cache = self.server.cache
        result: tuple[int, dict[str, Any]] | None = None

        status_match = STATUS_RE.fullmatch(path)
        detail_match = DETAIL_RE.fullmatch(path)
        list_match = LIST_RE.fullmatch(path)
        if path in {"/healthz", "/healthz/"}:
            result = (
                200,
                {
                    "service": "orca-gitcode-linker",
                    "ok": True,
                    "api_base": config.api_base,
                    "token_configured": bool(config.token),
                },
            )
        elif path in {"/version", "/version/"}:
            result = 200, {"version": "1.22.0"}
        elif path in {"/user", "/user/"}:
            result = 200, {"login": "gitcode", "username": "gitcode", "full_name": "GitCode"}
        elif status_match:
            sha = unquote(status_match.group(3))
            if not SHA_RE.fullmatch(sha):
                raise BadRequestError("Invalid commit SHA.")
            result = 200, neutral_commit_status(sha)
        elif detail_match:
            owner = _segment(detail_match.group(1), "owner")
            repo = _segment(detail_match.group(2), "repository")
            number = _number(detail_match.group(3))
            result = 200, load_pull(config, cache, self.server.meta_cache, self.server.source_map, owner, repo, number)
        elif list_match:
            owner = _segment(list_match.group(1), "owner")
            repo = _segment(list_match.group(2), "repository")
            state = _state_query(query)
            page = _int_query(query, "page", 1, 1, 1000)
            limit = _int_query(query, "limit", 30, 1, 100)
            result = (
                200,
                load_pulls(
                    config,
                    cache,
                    self.server.meta_cache,
                    self.server.source_map,
                    owner,
                    repo,
                    state,
                    page,
                    limit,
                ),
            )
        return result or (404, {"message": "Not found"})

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            with contextlib.suppress(BrokenPipeError):
                self.wfile.write(body)


class LinkerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: LinkerConfig):
        self.config = config
        self.cache = TtlCache(config.cache_ttl)
        self.meta_cache = TtlCache(3600)
        self.source_map = TtlCache(300)
        super().__init__(address, LinkerHandler)


def _read_token_file(path: str) -> str:
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8")
    except OSError:
        return ""
    return text.strip().splitlines()[0].strip() if text.strip() else ""


def _token_from_gc_config() -> tuple[str, str]:
    config_path = Path.home() / ".config" / "gc" / "config.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "", "none"
    if not isinstance(data, dict):
        return "", "none"
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip(), str(config_path)
    accounts = data.get("accounts")
    active = data.get("active_account")
    if isinstance(accounts, dict) and isinstance(active, str):
        token = accounts.get(active)
        if isinstance(token, str) and token.strip():
            return token.strip(), str(config_path)
    return "", "none"


def resolve_token(explicit: str | None, token_file: str | None) -> tuple[str, str]:
    token = ""
    source = "none"
    if explicit and explicit.strip():
        token, source = explicit.strip(), "--token"
    else:
        for env_name in ("GC_TOKEN", "ORCA_GITCODE_TOKEN"):
            value = os.environ.get(env_name, "").strip()
            if value:
                token, source = value, env_name
                break
    if not token:
        for candidate in (token_file, os.environ.get("ORCA_LINKER_TOKEN_FILE")):
            if candidate:
                value = _read_token_file(candidate)
                if value:
                    token, source = value, candidate
                    break
    if not token:
        token, source = _token_from_gc_config()
    return token, source
