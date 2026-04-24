from __future__ import annotations

from dataclasses import dataclass

from .client import GitCodeClient


@dataclass
class AppContext:
    token: str
    repo: str | None

    def client(self) -> GitCodeClient:
        return GitCodeClient(token=self.token)
