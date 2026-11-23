"""Thin GitCode repository discussion v5 calls; do not guess GitHub resource paths."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ..errors import APIError
from .repos import _repository_path, _segment

MAX_REPLY_PAGE = 100


def valid_comment_id(value: object) -> bool:
    """Require one literal, opaque GitCode comment ID, not a URL or encoded path."""
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and all(ch.isprintable() and not ch.isspace() and ch not in "/\\%?#:@" for ch in value)
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

    def replies_page(self, number: int, comment_id: str, *, page: int, per_page: int) -> Any:
        if type(number) is not int or number < 1 or not valid_comment_id(comment_id):
            raise APIError("Provide a positive discussion number and a literal GitCode comment ID.")
        if type(page) is not int or page < 1 or type(per_page) is not int or not 1 <= per_page <= MAX_REPLY_PAGE:
            raise APIError("Invalid page or page size for discussion replies.")
        return self.client.get(
            f"{self.path}/{number}/comment/{_segment(comment_id)}/reply", params={"page": page, "per_page": per_page}
        )

    def comment(self, number: int, body: str) -> Any:
        return self.client.post(f"{self.path}/{number}/comment", json={"md_content": body})
