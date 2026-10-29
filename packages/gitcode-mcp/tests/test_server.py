import json
import os
import subprocess
import sys

import httpx
import pytest
from mcp.client import Client
from starlette.testclient import TestClient

from gitcode_mcp.api import GitCodeAPI
from gitcode_mcp.config import ConfigurationError, Settings
from gitcode_mcp.server import create_http_app, create_server
from gitcode_mcp.tools import GitCodeTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_protocol_lists_schema_and_calls_api():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": 42, "full_name": "owner/repo"})

    with GitCodeAPI("secret", transport=httpx.MockTransport(handler)) as api:
        async with Client(create_server(Settings(), api=api)) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 31
            assert all(tool.input_schema["type"] == "object" for tool in tools)
            response = await client.call_tool(
                "gitcode_get_repository", {"owner": "owner", "repo": "repo"}
            )
            assert not response.is_error
            assert response.structured_content["data"]["id"] == 42
            assert json.loads(response.content[0].text) == response.structured_content
    assert len(calls) == 1
    assert calls[0].headers["Authorization"] == "Bearer secret"


@pytest.mark.anyio
async def test_read_only_and_allowlist_are_execution_controls():
    requests = []
    with GitCodeAPI(
        "secret", transport=httpx.MockTransport(lambda request: requests.append(request))
    ) as api:
        settings = Settings(read_only=True, allowed_repositories=("allowed/repo",))
        async with Client(create_server(settings, api=api)) as client:
            tools = (await client.list_tools()).tools
            assert all(tool.annotations.read_only_hint for tool in tools)
            denied_write = await client.call_tool(
                "gitcode_create_issue", {"owner": "allowed", "repo": "repo", "title": "A title"}
            )
            denied_repo = await client.call_tool(
                "gitcode_get_repository", {"owner": "other", "repo": "repo"}
            )
            assert denied_write.is_error and denied_repo.is_error
    assert requests == []


@pytest.mark.anyio
async def test_unexpected_errors_do_not_expose_arguments_or_exception(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("sensitive-exception-value")

    monkeypatch.setattr(GitCodeTools, "call", fail)
    with GitCodeAPI("") as api:
        async with Client(create_server(Settings(), api=api)) as client:
            response = await client.call_tool(
                "gitcode_get_repository", {"owner": "owner", "repo": "repo"}
            )
            assert response.is_error
            assert "sensitive-exception-value" not in response.model_dump_json()
            assert "sensitive-exception-value" not in caplog.text


def test_http_non_loopback_requires_separate_authentication():
    with GitCodeAPI("") as api:
        with pytest.raises(ConfigurationError, match="GITCODE_MCP_HTTP_TOKEN"):
            create_http_app(create_server(Settings(), api=api), Settings(), host="0.0.0.0")


def test_streamable_http_auth_host_validation_and_jsonrpc():
    token = "transport-token-for-this-test-only-1234"
    settings = Settings(http_token=token)
    with GitCodeAPI("") as api:
        app = create_http_app(create_server(settings, api=api), settings)
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
            }
            headers = {"Accept": "application/json, text/event-stream"}
            assert client.post("/mcp", json=payload, headers=headers).status_code == 401
            headers["Authorization"] = "Bearer wrong-token"
            assert client.post("/mcp", json=payload, headers=headers).status_code == 401
            headers["Authorization"] = "Bearer " + token
            response = client.post("/mcp", json=payload, headers=headers)
            assert response.status_code == 200
            assert response.json()["result"]["serverInfo"]["name"] == "codeasier-gitcode"
            catalog = client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers
            )
            assert len(catalog.json()["result"]["tools"]) == 31
            bad_host = client.post(
                "/mcp", json=payload, headers={**headers, "Host": "attacker.example"}
            )
            assert bad_host.status_code == 421
            bad_origin = client.post(
                "/mcp", json=payload, headers={**headers, "Origin": "https://attacker.example"}
            )
            assert bad_origin.status_code == 403


def test_installed_entrypoint_stdio_smoke():
    environment = dict(os.environ)
    for name in list(environment):
        if name.startswith("GITCODE_") or name == "GC_TOKEN":
            environment.pop(name)
    completed = subprocess.run(
        [sys.executable, "-I", "-m", "gitcode_mcp.smoke"],
        capture_output=True,
        text=True,
        timeout=45,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    assert "no network calls" in completed.stdout
