"""Bounded, repository-scoped personal issue queues. Mentions have no verified filter."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from .._redact import redact
from ..client import ISSUE_STATUS_LOGIN, ISSUE_STATUS_MAX_PAGE, ISSUE_STATUS_PAGE_SIZE
from ..errors import APIError, GCError
from ..repo_read import bounded_json_response, bounded_read_url, validate_target

PAGE_SIZE = ISSUE_STATUS_PAGE_SIZE
MAX_DATA_PAGES = ISSUE_STATUS_MAX_PAGE - 1
_LINK_URI = re.compile(r"\s*<([^<>]+)>\s*")
_LINK_PARAM = re.compile(r';\s*([\w-]+)(?:\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;,"\s]+)))?\s*')


StatusPageReader = Callable[[str, dict[str, str]], tuple[Any, httpx.Headers, httpx.URL]]


def _positive(value: Any) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return int(value)
    raise APIError("Issue status returned an invalid numeric identity.")


def _actor(value: Any) -> tuple[str, str]:
    login = value.get("login") if isinstance(value, dict) else None
    uid = value.get("id") if isinstance(value, dict) else None
    if type(uid) is int and uid > 0:
        uid = str(uid)
    if (
        not isinstance(login, str)
        or not ISSUE_STATUS_LOGIN.fullmatch(login)
        or not isinstance(uid, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", uid)
    ):
        raise APIError("Cannot verify a GitCode user ID and login for issue status.")
    return login, uid


def _literal(segment: Any) -> str:
    if not isinstance(segment, str):
        raise APIError("Cannot verify the issue repository path.")
    try:
        validate_target(segment, segment, None)
    except GCError:
        raise APIError("Cannot verify the issue repository path.") from None
    return segment


def _full_name_claim(full_name: Any) -> tuple[str, str] | None:
    if full_name is None:
        return None
    if not isinstance(full_name, str) or full_name.count("/") != 1 or not full_name.isprintable():
        raise APIError("Cannot verify the issue repository name.")
    owner, name = (part.strip(" ") for part in full_name.split("/"))
    if not owner or not name:
        raise APIError("Cannot verify the issue repository name.")
    # 'owner / repo' is a documented issue list fallback. Genuine display
    # components are not aliases: use separately supplied canonical paths.
    if " " in owner or " " in name:
        return None
    return _literal(owner), _literal(name)


def _repo(value: Any) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise APIError("Cannot verify the issue repository.")
    owners: set[str] = set()
    names: set[str] = set()
    for field in ("path_with_namespace", "full_path"):
        path = value.get(field)
        if path is None:
            continue
        if not isinstance(path, str) or path.count("/") != 1:
            raise APIError("Cannot verify the issue repository path.")
        owner, name = path.split("/")
        owners.add(_literal(owner))
        names.add(_literal(name))
    if value.get("path") is not None:
        names.add(_literal(value["path"]))
    namespace = value.get("namespace")
    if namespace is not None:
        if not isinstance(namespace, dict):
            raise APIError("Cannot verify the issue repository namespace.")
        for field in ("path", "full_path"):
            if namespace.get(field) is not None:
                owners.add(_literal(namespace[field]))
    full_name = _full_name_claim(value.get("full_name"))
    if full_name is not None:
        owners.add(full_name[0])
        names.add(full_name[1])
    if not owners or not names:
        raise APIError("Cannot verify the issue repository path.")
    if len(owners) != 1 or len(names) != 1:
        raise APIError("Conflicting repository identity in issue status.")
    return f"{owners.pop()}/{names.pop()}", _positive(value.get("id"))


def _link_parameters(header: str, offset: int, source: str) -> tuple[list[str], bool, int]:
    rels: list[str] = []
    anchored = False
    while param := _LINK_PARAM.match(header, offset):
        key = param[1].lower()
        if key == "rel":
            rels.append(param[2] or param[3] or "")
        elif key == "anchor":
            anchored = True
        offset = param.end()
    if len(rels) > 1 or (rels and not rels[0]):
        raise APIError(f"Ambiguous {source} pagination link.")
    return re.sub(r"\\(.)", r"\1", rels[0]).lower().split() if rels else [], anchored, offset


def _continuation_links(headers: httpx.Headers, source: str) -> dict[str, str]:
    links: dict[str, str] = {}
    for header in (value.strip() for value in headers.get_list("link")):
        offset = 0
        while offset < len(header):
            match = _LINK_URI.match(header, offset)
            if not match:
                raise APIError(f"Malformed {source} pagination link.")
            rels, anchored, offset = _link_parameters(header, match.end(), source)
            for rel in rels:
                if rel in ("first", "prev", "next", "last"):
                    if anchored or rel in links:
                        raise APIError(f"Ambiguous {source} pagination link.")
                    links[rel] = match[1]
            if offset < len(header):
                if header[offset] != "," or offset + 1 == len(header):
                    raise APIError(f"Malformed {source} pagination link.")
                offset += 1
    return links


def _linked_page(link: str, current: httpx.URL, source: str) -> int:
    try:
        if "\\" in link or any(char.isspace() or not char.isprintable() for char in link):
            raise ValueError
        if re.search(r"%(?![A-Fa-f0-9]{2})", link):
            raise ValueError
        parsed, requested = urlsplit(urljoin(str(current), link)), urlsplit(str(current))
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        normalized = dict(pairs)
        expected = dict(current.params)
        page = normalized.get("page", "")
        expected["page"] = page
        if (
            (parsed.scheme, parsed.netloc, parsed.path) != (requested.scheme, requested.netloc, requested.path)
            or "#" in link
            or len(pairs) != len(expected)
            or normalized != expected
            or not re.fullmatch(r"[1-9][0-9]{0,19}", page)
        ):
            raise ValueError
        return int(page)
    except ValueError:
        raise APIError(
            f"{source[0].upper() + source[1:]} pagination link disagrees with the requested scope or page."
        ) from None


def _header(headers: httpx.Headers, key: str, source: str) -> str | None:
    values = headers.get_list(key)
    if len(values) > 1:
        raise APIError(f"Duplicate {source} pagination header.")
    return values[0].strip() if values else None


def _validate_backward_links(
    links: dict[str, str], headers: httpx.Headers, url: httpx.URL, page: int, source: str
) -> None:
    previous = str(page - 1) if page > 1 else ""
    advertised_prev = _header(headers, "x-prev-page", source)
    if (
        advertised_prev not in (None, previous)
        or ("first" in links and _linked_page(links["first"], url, source) != 1)
        or ("prev" in links and (page == 1 or _linked_page(links["prev"], url, source) != page - 1))
    ):
        raise APIError(f"Conflicting {source} pagination first or previous page.")


class _Pagination:
    """Validate a bounded v5 status array while callers probe fixed, sequential URLs."""

    def __init__(self, *, page_size: int = PAGE_SIZE, source: str = "issue status") -> None:
        self.page_size = page_size
        self.source = source
        self.label = source[0].upper() + source[1:]
        self.seen_count = 0
        self.total: int | None = None
        self.total_pages: int | None = None
        self.ended = False
        self.expects_data = False

    def validate(self, items: Any, headers: httpx.Headers, url: httpx.URL) -> None:
        if not isinstance(items, list) or len(items) > self.page_size:
            raise APIError(f"Invalid {self.source} page.")
        page = int(url.params["page"])
        if _header(headers, "x-page", self.source) not in (None, str(page)) or _header(
            headers, "x-per-page", self.source
        ) not in (None, str(self.page_size)):
            raise APIError(f"GitCode did not confirm the requested {self.source} page.")
        advertised_next = _header(headers, "x-next-page", self.source)
        links = _continuation_links(headers, self.source)
        _validate_backward_links(links, headers, url, page, self.source)
        if advertised_next not in (None, "", str(page + 1)) or (
            "next" in links and (advertised_next == "" or _linked_page(links["next"], url, self.source) != page + 1)
        ):
            raise APIError(f"Conflicting {self.source} pagination continuation.")
        last = _linked_page(links["last"], url, self.source) if "last" in links else None
        self._read_totals(headers, last)
        if "content-range" in headers or any(
            _header(headers, key, self.source) not in (None, "false", "0")
            for key in ("x-truncated", "x-incomplete-results")
        ):
            raise APIError(f"GitCode reported incomplete {self.source} results.")
        self.seen_count += len(items)
        continuation = advertised_next == str(page + 1) or "next" in links
        self._validate_totals(bool(items), page, continuation, advertised_next == "")
        if (not items and (continuation or self.expects_data)) or (self.ended and items):
            raise APIError(f"{self.label} results contradict the pagination continuation.")
        self.expects_data = continuation
        self.ended = (
            advertised_next == ""
            or (self.total is not None and self.seen_count == self.total)
            or (self.total_pages is not None and page >= self.total_pages)
        )

    def _read_totals(self, headers: httpx.Headers, last: int | None) -> None:
        for key, state, other in (("x-total", "total", None), ("x-total-pages", "total_pages", last)):
            raw = _header(headers, key, self.source)
            if raw is not None and not re.fullmatch(r"0|[1-9][0-9]{0,19}", raw):
                raise APIError(f"Invalid {self.source} pagination total.")
            evidence = {
                value
                for value in (getattr(self, state), int(raw) if raw is not None else None, other)
                if value is not None
            }
            if len(evidence) > 1:
                raise APIError(f"Conflicting {self.source} pagination totals.")
            if evidence:
                setattr(self, state, evidence.pop())

    def _validate_totals(self, data: bool, page: int, continuation: bool, explicit_end: bool) -> None:
        if self.total is not None:
            if self.seen_count > self.total or (not data and self.seen_count < self.total):
                raise APIError(f"{self.label} results disagree with the reported total.")
            if (continuation and self.seen_count == self.total) or (explicit_end and self.seen_count < self.total):
                raise APIError(f"{self.label} continuation disagrees with the reported total.")
        if self.total_pages is not None:
            if self.total is not None and not (
                self.total_pages <= self.total <= self.total_pages * self.page_size
                or self.total == 0
                and self.total_pages == 1
            ):
                raise APIError(f"{self.label} results disagree with the reported page and row counts.")
            if (data and page > self.total_pages) or (
                not data
                and page <= self.total_pages
                and not (page == 1 == self.total_pages and self.total in (None, 0))
            ):
                raise APIError(f"{self.label} results disagree with the reported page count.")
            if (continuation and page >= self.total_pages) or (explicit_end and page < self.total_pages):
                raise APIError(f"{self.label} continuation disagrees with the reported page count.")


def _matches(value: Any, expected: tuple[str, str]) -> bool:
    login, uid = _actor(value)
    if (login == expected[0]) != (uid == expected[1]):
        raise APIError("Conflicting actor identity in issue status.")
    return (login, uid) == expected


def _text(value: Any, token: str) -> str:
    if not isinstance(value, str):
        raise APIError("Invalid text in issue status.")
    # Terminal, jq and template output must never include control codes or the credential.
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in redact(value, token))


def _row(row: Any, repo: tuple[str, int], actor: tuple[str, str], group: str, token: str) -> dict:
    if not isinstance(row, dict) or _repo(row.get("repository")) != repo:
        raise APIError("Issue response does not match the requested repository.")
    number = _positive(row.get("number"))
    if row.get("state") not in ("open", "opened"):
        raise APIError("Could not verify an open issue.")
    if "html_url" in row:
        try:
            parsed = urlsplit(row["html_url"]) if isinstance(row["html_url"], str) else None
            valid = (
                parsed
                and parsed.scheme == "https"
                and parsed.netloc in ("gitcode.com", "api.gitcode.com", "atomgit.com", "api.atomgit.com")
                and not parsed.query
                and not parsed.fragment
                and parsed.path == f"/{repo[0]}/issues/{number}"
            )
        except ValueError:
            valid = False
        if not valid:
            raise APIError("Conflicting issue URL in issue status.")
    if group == "assigned":
        people = row.get("assignees", [])
        if not isinstance(people, list):
            raise APIError("Invalid issue assignee list.")
        actors = ([row["assignee"]] if row.get("assignee") is not None else []) + people
    else:
        actors = [row.get("user")]
    # Validate every actor, including entries after the first positive match.
    matches = [_matches(person, actor) for person in actors]
    if not any(matches):
        raise APIError("GitCode did not confirm the requested user filter.")
    title = _text(row.get("title"), token)
    labels = row.get("labels", [])
    if not title.strip() or not isinstance(labels, list) or not all(isinstance(label, dict) for label in labels):
        raise APIError("Invalid issue status summary.")
    return {
        "id": _positive(row.get("id")),
        "number": row["number"],
        "title": title,
        "state": row["state"],
        "created_at": _text(row.get("created_at", ""), token),
        "labels": [{"name": _text(label.get("name"), token)} for label in labels],
    }


def status(owner: str, name: str, token: str, *, read_page: StatusPageReader | None = None) -> dict:
    validate_target(owner, name, None)
    if not token:
        raise APIError("Issue status requires authentication. Run 'gc auth login'.")

    def read(endpoint: str, params: dict[str, str]) -> tuple[Any, httpx.Headers, httpx.URL]:
        expected = bounded_read_url(endpoint, params)
        value, headers, url = (
            read_page(endpoint, dict(params))
            if read_page is not None
            else bounded_json_response("Issue status", endpoint, params, token, (endpoint, *params.values()))
        )
        if url != expected:
            raise APIError("Issue status transport returned a different request scope.")
        return value, headers, url

    requested = f"{owner}/{name}"
    endpoint = f"/repos/{requested}"
    identity = _repo(read(endpoint, {})[0])
    # Allow ASCII case aliases only after the requested repo's metadata supplies
    # its canonical path and ID. All rows must then match both exactly.
    if identity[0].lower() != requested.lower():
        raise APIError("GitCode did not confirm the requested repository.")
    actor = _actor(read("/user", {})[0])
    result: dict[str, Any] = {"mentioned": None}
    numbers: dict[int, int] = {}
    ids: dict[int, int] = {}
    # The repository issue route accepts the account login for both selectors.
    # The opaque ID is still required to verify row identity; never retry with it.
    for group, param in (("assigned", "assignee"), ("createdBy", "creator")):
        seen: set[int] = set()
        rows = []
        pagination = _Pagination()
        path = f"/repos/{identity[0]}/issues"
        for page in range(1, MAX_DATA_PAGES + 2):
            params = {param: actor[0], "state": "open", "page": str(page), "per_page": str(PAGE_SIZE)}
            items, headers, url = read(path, params)
            pagination.validate(items, headers, url)
            if not items:
                break
            if page > MAX_DATA_PAGES:
                raise APIError("Issue status exceeded the page limit; no partial report was printed.")
            for item in items:
                row = _row(item, identity, actor, group, token)
                number, uid = int(row["number"]), row["id"]
                if number in seen or numbers.setdefault(number, uid) != uid or ids.setdefault(uid, number) != number:
                    raise APIError("Duplicate or conflicting issue identity during pagination.")
                seen.add(number)
                rows.append(row)
        result[group] = rows
    return result
