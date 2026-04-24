"""Tests for gitcode_cli.context module."""

from __future__ import annotations

from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext


class TestAppContext:
    def test_dataclass_creation(self):
        ctx = AppContext(token="my-token", repo="owner/repo")
        assert ctx.token == "my-token"
        assert ctx.repo == "owner/repo"

    def test_dataclass_creation_without_repo(self):
        ctx = AppContext(token="my-token", repo=None)
        assert ctx.token == "my-token"
        assert ctx.repo is None

    def test_client_returns_gitcode_client(self):
        ctx = AppContext(token="my-token", repo=None)
        client = ctx.client()
        assert isinstance(client, GitCodeClient)
        assert client.token == "my-token"
