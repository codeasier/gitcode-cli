from __future__ import annotations

from typing import Any

from ..client import GitCodeClient


class UserService:
    def __init__(self, client: GitCodeClient):
        self.client = client

    def current(self) -> Any | None:
        return self.client.get("/user")
