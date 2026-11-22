"""The current user's organizations (GitCode uses /users/orgs, not /user/orgs)."""

from __future__ import annotations

from typing import Any

from ..client import GitCodeClient


class OrganizationService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def list_page(self, *, page: int, per_page: int) -> Any:
        return self.client.get("/users/orgs", params={"page": page, "per_page": per_page})
