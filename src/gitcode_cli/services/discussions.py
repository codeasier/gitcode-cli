"""Thin GitCode repository discussion v5 calls; do not guess GitHub resource paths."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from .repos import _repository_path


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

    def comment(self, number: int, body: str) -> Any:
        return self.client.post(f"{self.path}/{number}/comment", json={"md_content": body})
