"""Repository Webhook primitives; caller owns identity, policy and recovery."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient
from ._pagination import collect_pages


class WebhookService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list_all(self, owner: str, repo: str) -> list[Any]:
        return collect_pages(self.client, f"/repos/{owner}/{repo}/hooks")

    def create(self, owner: str, repo: str, **data: Any) -> Any | None:
        return self.client.post(f"/repos/{owner}/{repo}/hooks", json=data)
