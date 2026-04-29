"""Tests for gitcode_cli.client module."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx
from httpx import Response

from gitcode_cli.client import BASE_URL, GitCodeClient
from gitcode_cli.errors import APIError, NetworkError


class TestGitCodeClientInit:
    def test_init_default_base_url(self):
        client = GitCodeClient(token="test-token")
        assert client.token == "test-token"
        assert client.base_url == BASE_URL
        assert client._client is not None

    def test_init_custom_base_url(self):
        custom_url = "https://custom.gitcode.com/api/"
        client = GitCodeClient(token="test-token", base_url=custom_url)
        assert client.base_url == custom_url


class TestGitCodeClientMethods:
    @pytest.fixture
    def client(self) -> GitCodeClient:
        return GitCodeClient(token="test-token", base_url="https://api.gitcode.com/api/v5/")

    def test_get_success(self, client: GitCodeClient):
        with respx.mock:
            route = respx.get("https://api.gitcode.com/api/v5/repos/owner/repo/issues").mock(
                return_value=Response(200, json={"id": 1})
            )
            result = client.get("repos/owner/repo/issues")
            assert result == {"id": 1}
            assert "access_token" in route.calls.last.request.url.params
            assert route.calls.last.request.url.params["access_token"] == "test-token"

    def test_post_success(self, client: GitCodeClient):
        with respx.mock:
            route = respx.post("https://api.gitcode.com/api/v5/repos/owner/repo/issues").mock(
                return_value=Response(201, json={"id": 2})
            )
            result = client.post("repos/owner/repo/issues", json={"title": "Test"})
            assert result == {"id": 2}
            assert route.calls.last.request.url.params["access_token"] == "test-token"

    def test_patch_success(self, client: GitCodeClient):
        with respx.mock:
            respx.patch("https://api.gitcode.com/api/v5/repos/owner/repo/issues/1").mock(
                return_value=Response(200, json={"id": 1, "title": "Updated"})
            )
            result = client.patch("repos/owner/repo/issues/1", json={"title": "Updated"})
            assert result == {"id": 1, "title": "Updated"}

    def test_put_success(self, client: GitCodeClient):
        with respx.mock:
            respx.put("https://api.gitcode.com/api/v5/repos/owner/repo/issues/1").mock(
                return_value=Response(200, json={"id": 1})
            )
            result = client.put("repos/owner/repo/issues/1", json={"state": "closed"})
            assert result == {"id": 1}

    def test_delete_success(self, client: GitCodeClient):
        with respx.mock:
            respx.delete("https://api.gitcode.com/api/v5/repos/owner/repo/issues/1").mock(return_value=Response(204))
            result = client.delete("repos/owner/repo/issues/1")
            assert result is None

    def test_text_response_returns_text(self, client: GitCodeClient):
        with respx.mock:
            route = respx.get("https://api.gitcode.com/api/v5/repos/owner/repo/pulls/42/diff").mock(
                return_value=Response(200, text="diff --git a/file b/file\n")
            )
            result = client.request(
                "GET",
                "repos/owner/repo/pulls/42/diff",
                accept="text/plain",
                response_format="text",
            )
            assert result == "diff --git a/file b/file\n"
            assert route.calls.last.request.headers["accept"] == "text/plain"

    def test_api_error_with_json_body(self, client: GitCodeClient):
        with respx.mock:
            respx.get("https://api.gitcode.com/api/v5/error").mock(
                return_value=Response(400, json={"message": "Bad request"})
            )
            with pytest.raises(APIError, match="Bad request"):
                client.get("error")

    def test_api_error_with_non_json_body(self, client: GitCodeClient):
        with respx.mock:
            respx.get("https://api.gitcode.com/api/v5/error").mock(
                return_value=Response(500, text="Internal Server Error")
            )
            with pytest.raises(APIError, match="Internal Server Error"):
                client.get("error")

    def test_api_error_empty_body(self, client: GitCodeClient):
        with respx.mock:
            respx.get("https://api.gitcode.com/api/v5/error").mock(return_value=Response(400, text=""))
            with pytest.raises(APIError, match="GitCode API request failed"):
                client.get("error")

    def test_access_token_always_included(self, client: GitCodeClient):
        with respx.mock:
            route = respx.get("https://api.gitcode.com/api/v5/test").mock(return_value=Response(200, json={}))
            client.get("test", params={"foo": "bar"})
            params = dict(route.calls.last.request.url.params)
            assert "access_token" in params
            assert params["access_token"] == "test-token"

    def test_none_params_filtered_out(self, client: GitCodeClient):
        with respx.mock:
            route = respx.get("https://api.gitcode.com/api/v5/test").mock(return_value=Response(200, json={}))
            client.get("test", params={"foo": "bar", "baz": None})
            params = dict(route.calls.last.request.url.params)
            assert "foo" in params
            assert "baz" not in params

    def test_params_merged_correctly(self, client: GitCodeClient):
        with respx.mock:
            route = respx.get("https://api.gitcode.com/api/v5/test").mock(return_value=Response(200, json={}))
            client.get("test", params={"page": 1, "per_page": 20})
            params = dict(route.calls.last.request.url.params)
            assert params["access_token"] == "test-token"
            assert params["page"] == "1"
            assert params["per_page"] == "20"


class TestNetworkErrorWrapping:
    def test_connect_error_raises_network_error(self):
        client = GitCodeClient(token="fake")
        client._client = MagicMock()
        client._client.request.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(NetworkError, match="Connection failed"):
            client.get("/test")

    def test_timeout_raises_network_error(self):
        client = GitCodeClient(token="fake")
        client._client = MagicMock()
        client._client.request.side_effect = httpx.TimeoutException("Timed out")

        with pytest.raises(NetworkError, match="Request timed out"):
            client.get("/test")

    def test_401_raises_api_error_with_auth_message(self):
        client = GitCodeClient(token="invalid")
        client._client = MagicMock()
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"message": "Unauthorized"}
        response.content = b'{"message":"Unauthorized"}'
        client._client.request.return_value = response

        with pytest.raises(APIError, match="Authentication failed: Unauthorized"):
            client.get("/test")
