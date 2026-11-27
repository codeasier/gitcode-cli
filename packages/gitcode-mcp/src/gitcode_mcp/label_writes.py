"""Bounded repository label mutations; no Issue assignment, retries or force-upserts."""

from __future__ import annotations

import re
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlsplit

import httpx
from pydantic import AfterValidator, Field

from .api import API_BASE_URL, GitCodeAPI, GitCodeError, segment

LABEL_WRITE_METHODS = frozenset({"create_label", "update_label", "delete_label"})
_PAGE_SIZE = 100
_MAX_PAGES = 10


def _name(value: str) -> str:
    if (
        value in {".", ".."}
        or value != value.strip()
        or not value.isprintable()
        or any(c in value for c in "/\\%,?#")
    ):
        raise ValueError("Expected a single literal label name.")
    return value


def _color(value: str) -> str:
    if not re.fullmatch(r"#?[a-fA-F0-9]{6}", value):
        raise ValueError("Expected a six-digit RGB hex color.")
    return "#" + value.lstrip("#").upper()


LabelName = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(_name)]
LabelColor = Annotated[str, Field(min_length=6, max_length=7), AfterValidator(_color)]


def _invalid() -> GitCodeError:
    return GitCodeError("invalid_response", "Could not verify the repository task-label catalog.")


def _uncertain() -> GitCodeError:
    return GitCodeError(
        "unverified_write",
        "The repository label mutation could not be verified.",
        operation_may_have_completed=True,
    )


def _integer(value: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", value):
        raise _invalid()
    return int(value)


def _links(headers: httpx.Headers, url: str) -> dict[str, int]:
    # Consume only canonical numbered pagination links as evidence. Never follow one.
    out: dict[str, int] = {}
    for line in headers.get_list("link"):
        for token in line.split(","):
            match = re.fullmatch(r'\s*<([^<>\s]+)>;\s*rel="?(next|last|prev|first)"?\s*', token)
            if not match or match[2] in out:
                raise _invalid()
            try:
                target = urlsplit(match[1])
            except ValueError:
                raise _invalid() from None
            if target.query == "" or match[1].split("?", 1)[0] != url or target.fragment:
                raise _invalid()
            query = sorted(parse_qsl(target.query, keep_blank_values=True))
            if (
                len(query) != 2
                or query[0][0] != "page"
                or query[1] != ("per_page", str(_PAGE_SIZE))
            ):
                raise _invalid()
            out[match[2]] = _integer(query[0][1])
    return out


def _catalog(api: GitCodeAPI, path: str) -> dict[int, str]:
    seen: dict[int, str] = {}
    names: set[str] = set()
    total = pages = repo_id = None
    terminal = has_next = False
    for page in range(1, _MAX_PAGES + 2):
        rows, h = api.task_label_request("GET", path, params={"page": page, "per_page": _PAGE_SIZE})
        if not isinstance(rows, list) or len(rows) > _PAGE_SIZE or "content-range" in h:
            raise _invalid()
        if h.get("x-page", str(page)) != str(page) or h.get("x-per-page", str(_PAGE_SIZE)) != str(
            _PAGE_SIZE
        ):
            raise _invalid()
        if any(
            h.get(k, "false").lower() not in ("false", "0")
            for k in ("x-truncated", "x-incomplete-results")
        ):
            raise _invalid()
        links = _links(h, API_BASE_URL + path.lstrip("/"))
        if links.get("first", 1) != 1 or (
            "prev" in links and (page <= 1 or links["prev"] != page - 1)
        ):
            raise _invalid()
        if "x-prev-page" in h and h["x-prev-page"] != ("" if page == 1 else str(page - 1)):
            raise _invalid()
        if "x-total" in h:
            new_total = _integer(h["x-total"])
            if total is not None and new_total != total:
                raise _invalid()
            total = new_total
        for last in (h.get("x-total-pages"), str(links["last"]) if "last" in links else None):
            if last is not None:
                last_number = _integer(last)
                if pages is not None and last_number != pages:
                    raise _invalid()
                pages = last_number
        next_value = h.get("x-next-page")
        if next_value not in (None, "", str(page + 1)) or (
            "next" in links and (links["next"] != page + 1 or next_value == "")
        ):
            raise _invalid()
        advertised_next = "next" in links or bool(next_value)
        if not rows:
            if has_next or advertised_next or (total is not None and total != len(seen)):
                raise _invalid()
            if pages is not None and pages != page - 1 and not (page == 1 == pages):
                raise _invalid()
            return seen
        if terminal or page > _MAX_PAGES or (pages is not None and page > pages):
            raise _invalid()
        for row in rows:
            if not isinstance(row, dict):
                raise _invalid()
            identity, name = row.get("id"), row.get("name")
            if (
                type(identity) is not int
                or identity < 1
                or identity in seen
                or not isinstance(name, str)
                or not name
                or not name.isprintable()
                or name.casefold() in names
            ):
                raise _invalid()
            if "repository_id" in row:
                current_id = row["repository_id"]
                if (
                    type(current_id) is not int
                    or current_id < 1
                    or (repo_id is not None and repo_id != current_id)
                ):
                    raise _invalid()
                repo_id = current_id
            seen[identity] = name
            names.add(name.casefold())
        if total is not None and len(seen) > total:
            raise _invalid()
        terminal = next_value == "" or pages == page or total == len(seen)
        if terminal and advertised_next:
            raise _invalid()
        has_next = advertised_next
    raise _invalid()


def write_label(api: GitCodeAPI, prefix: str, action: str, data: dict[str, Any]) -> dict:
    path = f"{prefix}/labels"
    # PATCH's documented name/color are query parameters. Do not transmit a credential
    # supplied in a label value in a URL, even under an otherwise allowed query key.
    if api.token and any(api.token in value for value in data.values() if isinstance(value, str)):
        raise GitCodeError("invalid_arguments", "Label arguments must not contain credentials.")
    name = data["name"]
    expected_id = data.get("expected_id")
    if action != "create_label":
        before = _catalog(api, path)
        if before.get(expected_id) != name:
            raise GitCodeError(
                "conflict", "The expected label ID and name do not match. No write sent."
            )
        target = data.get("new_name", name).casefold()
        if any(i != expected_id and n.casefold() == target for i, n in before.items()):
            raise GitCodeError(
                "conflict", "The new name already belongs to another label. No write sent."
            )
    if action == "delete_label":
        result, _ = api.task_label_request("DELETE", f"{path}/{segment(name)}")
        if result != {} and result is not None:
            raise _uncertain()
        try:
            after = _catalog(api, path)
        except GitCodeError:
            raise _uncertain() from None
        if expected_id in after or any(n.casefold() == name.casefold() for n in after.values()):
            raise _uncertain()
        return {"id": expected_id, "name": name, "readback": "absent_from_observed_catalog"}
    target_name = data.get("new_name", name)
    if action == "create_label":
        result, _ = api.task_label_request(
            "POST", path, form={"name": name, "color": data["color"]}
        )
    else:
        query = {k: data[v] for k, v in (("name", "new_name"), ("color", "color")) if v in data}
        result, _ = api.task_label_request("PATCH", f"{path}/{segment(name)}", params=query)
    if not isinstance(result, dict):
        raise _uncertain()
    identity, color = result.get("id"), result.get("color")
    if (
        type(identity) is not int
        or identity < 1
        or (expected_id is not None and expected_id != identity)
        or result.get("name") != target_name
        or not isinstance(color, str)
        or not re.fullmatch(r"#(?:[A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})", color)
        or ("color" in data and color.upper() != data["color"])
    ):
        raise _uncertain()
    return {"id": identity, "name": target_name, "color": color, "verification": "mutation_receipt"}
