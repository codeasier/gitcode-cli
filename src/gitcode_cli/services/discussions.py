"""Thin GitCode repository discussion v5 calls; do not guess GitHub resource paths."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ..errors import APIError, NetworkError
from .repos import _repository_path, _segment

MAX_REPLY_PAGE = 100
_PARENT_PAGE_SIZE = 100
_MAX_PARENT_PAGES = 10


def valid_comment_id(value: object) -> bool:
    """Require one literal, opaque GitCode comment ID, not a URL or encoded path."""
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and all(ch.isprintable() and not ch.isspace() and ch not in "/\\%?#:@" for ch in value)
    )


def _is_visible_root_comment(row: dict[str, Any]) -> bool:
    # A GET list row need not have the write schema's type/parent_id fields.
    # If supplied, they must not contradict what the top-level list proves.
    kind = row.get("type", 1)
    return (
        type(kind) is int
        and kind == 1
        and row.get("parent_id", "") == ""
        and all(type(row.get(key)) is int and row[key] == 0 for key in ("is_hide", "is_deleted"))
    )


class DiscussionService:
    def __init__(self, client: GitCodeClient, owner: str, repo: str):
        self.client = client
        self.path = _repository_path(owner, repo) + "/discuss"

    def list_page(self, **params: Any) -> Any:
        return self.client.get(self.path, params=params)

    def get(self, number: int) -> Any:
        return self.client.get(f"{self.path}/{number}")

    def create(self, title: str, body: str, category: str) -> Any:
        return self.client.post(self.path, json={"title": title, "md_content": body, "category_name": category})

    def edit(self, number: int, title: str, body: str, category: str) -> Any:
        return self.client.put(
            f"{self.path}/{number}", json={"title": title, "md_content": body, "category_name": category}
        )

    def comments_page(self, number: int, **params: Any) -> Any:
        return self.client.get(f"{self.path}/{number}/comment", params=params)

    def _verify_parent(self, number: int, comment_id: str) -> None:
        # A successful replies request alone is not proof of discussion membership.
        # Discard comment content; retain only IDs for bounded pagination checks.
        seen: set[str] = set()
        for page in range(1, _MAX_PARENT_PAGES + 1):
            try:
                rows = self.comments_page(number, order="time_asc", page=page, per_page=_PARENT_PAGE_SIZE)
            except APIError as exc:
                status = f" (HTTP {exc.status_code})" if exc.status_code else ""
                raise APIError(
                    f"Cannot verify the parent comment{status}; no replies requested.", exc.status_code
                ) from None
            except NetworkError:
                raise NetworkError("Cannot verify the parent comment: network error; no replies requested.") from None
            if not isinstance(rows, list) or len(rows) > _PARENT_PAGE_SIZE:
                raise APIError("Invalid discussion comment page; no replies requested.")
            found = False
            for row in rows:
                identity = row.get("id") if isinstance(row, dict) else None
                if not isinstance(identity, str) or not valid_comment_id(identity) or identity in seen:
                    raise APIError("Invalid or repeated discussion comment ID; no replies requested.")
                seen.add(identity)
                if identity == comment_id:
                    if not _is_visible_root_comment(row):
                        raise APIError(
                            "Cannot verify a visible top-level parent in this discussion; no replies requested."
                        )
                    found = True
            if found:
                return
            if len(rows) < _PARENT_PAGE_SIZE:
                raise APIError("Parent comment not found in the requested discussion; no replies requested.")
        raise APIError("Parent not verified within the discussion comment page limit; no replies requested.")

    def replies_page(self, number: int, comment_id: str, *, page: int, per_page: int) -> Any:
        if type(number) is not int or number < 1 or not valid_comment_id(comment_id):
            raise APIError("Provide a positive discussion number and a literal GitCode comment ID.")
        if type(page) is not int or page < 1 or type(per_page) is not int or not 1 <= per_page <= MAX_REPLY_PAGE:
            raise APIError("Invalid page or page size for discussion replies.")
        self._verify_parent(number, comment_id)
        return self.client.get(
            f"{self.path}/{number}/comment/{_segment(comment_id)}/reply", params={"page": page, "per_page": per_page}
        )

    def comment(self, number: int, body: str) -> Any:
        return self.client.post(f"{self.path}/{number}/comment", json={"md_content": body})
