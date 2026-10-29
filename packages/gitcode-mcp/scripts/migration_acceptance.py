"""Offline acceptance of installed artifacts, not a production migration utility.

Run ``smoke`` in a clean wheel/sdist venv. Run ``seed NEW_DIRECTORY`` with the
immutable old installation, wait for it to exit, then run ``verify DIRECTORY``
with the new installation. The fixture is disposable: all identities, tokens,
client secrets and its Fernet key are generated here, never loaded from .env or
an operator database. CI deletes it and uploads distributions only.

HTTP checks use the real ASGI/protocol boundary in-process, without a listener.
stdio uses the installed console entry point in a separate isolated process.
Both reject socket networking; these are not live GitCode acceptance tests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PACKAGE = "codeasier-gitcode-mcp"
LEGACY_VERSION = "0.3.0"
LEGACY_CLI_VERSION = "0.1.6"
CLI_VERSION = "0.1.7"
# Archive metadata is checked against source before installation. The installed
# version can advance while the immutable legacy seed remains exactly 0.3.0.
VERSION = importlib.metadata.version(PACKAGE)
LEGACY_SHA = "f93b67bb7048e556b44322d48664522f32651920"
MARKER = b"codeasier-gitcode-mcp.oauth-store.v1"
FIXTURE_FORMAT = "gitcode-mcp-migration-synthetic-v1"
READ_TOOLS = {
    "get_repository",
    "get_clone_info",
    "list_branches",
    "get_branch",
    "get_file_contents",
    "get_repository_tree",
    "list_commits",
    "get_commit",
    "list_issues",
    "get_issue",
    "list_issue_comments",
    "list_labels",
    "list_milestones",
    "list_pull_requests",
    "get_pull_request",
    "list_pull_request_files",
    "get_pull_request_diff",
    "list_pull_request_comments",
    "list_pull_request_commits",
}
WRITE_TOOLS = {
    "create_branch",
    "create_file",
    "update_file",
    "delete_file",
    "create_issue",
    "update_issue",
    "add_issue_comment",
    "create_pull_request",
    "update_pull_request",
    "add_pull_request_comment",
    "approve_pull_request",
    "merge_pull_request",
}


def isolate_process() -> None:
    # Read only this small nonsecret allowlist, never snapshot os.environ.
    environment = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    os.environ.clear()
    os.environ.update(environment)

    def deny_network(event: str, args: tuple[Any, ...]) -> None:
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise AssertionError("Offline acceptance attempted socket networking")

    sys.addaudithook(deny_network)


def installed_metadata(*, legacy: bool = False, license_required: bool = False) -> None:
    import gitcode_mcp

    distribution = importlib.metadata.distribution(PACKAGE)
    assert distribution.version == gitcode_mcp.__version__ == VERSION
    # Both installations can be MCP 0.3.0; select the dependency by role, never
    # infer legacy status from the MCP version or accept either pin everywhere.
    cli_version = LEGACY_CLI_VERSION if legacy else CLI_VERSION
    assert importlib.metadata.version("pygitcode") == cli_version
    assert distribution.metadata["Requires-Python"] == ">=3.11"
    requirements = [value.replace(" ", "") for value in distribution.requires or []]
    assert f"pygitcode=={cli_version}" in requirements
    entries = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }
    assert entries == {
        "gitcode-mcp": "gitcode_mcp.__main__:main",
        "gitcode-clone": "gitcode_mcp.clone:main",
    }
    assert Path(gitcode_mcp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    if license_required:
        licenses = [
            path
            for path in distribution.files or []
            if path.name == "LICENSE" and any(part.endswith(".dist-info") for part in path.parts)
        ]
        assert licenses, "Installed distribution must preserve the original MIT license"
        assert any(
            "MIT License" in distribution.locate_file(path).read_text(encoding="utf-8")
            and "codeasier" in distribution.locate_file(path).read_text(encoding="utf-8").lower()
            for path in licenses
        )


def check_catalog(tools: list[dict[str, Any]], read_only: bool = False) -> None:
    expected_read = {"gitcode_" + name for name in READ_TOOLS}
    expected_write = {"gitcode_" + name for name in WRITE_TOOLS}
    assert len(expected_read) == 19 and len(expected_write) == 12
    assert len(tools) == (19 if read_only else 31)
    assert {tool["name"] for tool in tools} == expected_read | (
        set() if read_only else expected_write
    )
    for tool in tools:
        assert tool["annotations"]["readOnlyHint"] is (tool["name"] in expected_read)
        assert tool["inputSchema"]["type"] == "object"


async def stdio_smoke(read_only: bool) -> None:
    import anyio
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-I", str(Path(__file__).resolve()), "_stdio", str(int(read_only))],
        env={name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ},
    )
    with anyio.fail_after(30):
        async with Client(parameters) as client:
            tools = (await client.list_tools()).tools
            check_catalog([tool.model_dump(by_alias=True) for tool in tools], read_only)
            invalid = await client.call_tool(
                "gitcode_get_repository", {"owner": "../escape", "repo": "fixture"}
            )
            assert invalid.is_error
            assert invalid.structured_content["error"]["code"] == "invalid_arguments"
            if read_only:
                denied = await client.call_tool(
                    "gitcode_create_issue",
                    {"owner": "fixture", "repo": "fixture", "title": "Not a live write"},
                )
                assert denied.is_error
                assert denied.structured_content["error"]["code"] == "read_only"


def http_smoke(read_only: bool) -> None:
    import httpx
    from starlette.testclient import TestClient

    from gitcode_mcp.api import GitCodeAPI
    from gitcode_mcp.config import Settings
    from gitcode_mcp.server import create_http_app, create_server

    requests = []

    def reject_api(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("Offline smoke must not call the GitCode API")

    token = secrets.token_urlsafe(32)
    settings = Settings(http_token=token, read_only=read_only)
    with GitCodeAPI("", transport=httpx.MockTransport(reject_api)) as api:
        app = create_http_app(create_server(settings, api=api), settings)
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            headers = {
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            }
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "migration-offline", "version": "1"},
                },
            }
            assert client.post("/mcp", json=payload, headers=headers).status_code == 401
            headers["Authorization"] = "Bearer " + token
            response = client.post("/mcp", json=payload, headers=headers)
            assert response.status_code == 200
            assert response.json()["result"]["serverInfo"]["version"] == VERSION
            notified = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=headers,
            )
            assert notified.status_code == 202
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers=headers,
            )
            assert response.status_code == 200
            check_catalog(response.json()["result"]["tools"], read_only)
            assert (
                client.post(
                    "/mcp", json=payload, headers={**headers, "Host": "attacker.example"}
                ).status_code
                == 421
            )
            assert (
                client.post(
                    "/mcp", json=payload, headers={**headers, "Origin": "https://attacker.example"}
                ).status_code
                == 403
            )
    assert not requests


def smoke() -> None:
    import anyio

    installed_metadata(license_required=True)
    for name in ("gitcode-mcp", "gitcode-clone"):
        executable = Path(sys.executable).parent / name
        result = subprocess.run(
            [str(executable), "--help"], check=True, capture_output=True, text=True, timeout=10
        )
        assert "usage:" in result.stdout.lower()
    for read_only in (False, True):
        anyio.run(stdio_smoke, read_only)
        http_smoke(read_only)
    print(
        "Installed wheel/sdist: metadata, license, both CLIs, stdio/HTTP 31/19/12 passed (offline)"
    )


class OfflineUpstream:
    """A fail-closed substitute: migration must reuse the persisted upstream token."""

    async def refresh(self, token: str) -> None:
        raise AssertionError("Migration unexpectedly attempted upstream refresh")

    async def user(self, token: str) -> None:
        raise AssertionError("Migration unexpectedly attempted upstream identity lookup")

    async def aclose(self) -> None:
        pass


def provider_for(manifest: dict[str, Any], directory: Path):
    from gitcode_mcp.config import Settings
    from gitcode_mcp.oauth import GitCodeOAuthProvider

    # This mapping is generated by seed, not copied from the environment.
    settings = Settings.from_env(
        {
            **manifest["configuration"],
            "GITCODE_MCP_OAUTH_DATABASE": str(directory / "synthetic-oauth.sqlite3"),
        }
    )
    return GitCodeOAuthProvider(settings, upstream=OfflineUpstream())


def store_format(directory: Path, manifest: dict[str, Any]) -> str:
    from cryptography.fernet import Fernet

    path = directory / "synthetic-oauth.sqlite3"
    assert not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600
    cipher = Fernet(manifest["configuration"]["GITCODE_MCP_OAUTH_ENCRYPTION_KEY"].encode())
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        marker = connection.execute("SELECT value FROM oauth_metadata WHERE id = 1").fetchone()[0]
        assert cipher.decrypt(marker) == MARKER
        rows = connection.execute("SELECT kind, key, value, expires FROM oauth_records").fetchall()
    for kind, key, value, expires in rows:
        assert len(key) == 64 and set(key) <= set("0123456789abcdef")
        envelope = json.loads(cipher.decrypt(value))
        assert set(envelope) == {"kind", "key", "expires", "payload"}
        assert (envelope["kind"], envelope["key"], envelope["expires"]) == (kind, key, expires)
    for kind, raw in (("grant", manifest["grant_id"]), ("access", manifest["access_token"])):
        assert any(row[:2] == (kind, hashlib.sha256(raw.encode()).hexdigest()) for row in rows)
    # Neither the old metadata marker nor the encryption key is rewritten at takeover.
    return hashlib.sha256(marker).hexdigest()


async def seed(directory: Path) -> None:
    from cryptography.fernet import Fernet

    directory.mkdir(mode=0o700, exist_ok=False)
    manifest = {
        "fixture_format": FIXTURE_FORMAT,
        "legacy_sha": LEGACY_SHA,
        "grant_id": secrets.token_urlsafe(32),
        "upstream_access": secrets.token_urlsafe(32),
        "configuration": {
            "GITCODE_MCP_AUTH_MODE": "oauth",
            "GITCODE_MCP_PUBLIC_URL": "https://migration.example.test",
            "GITCODE_OAUTH_CLIENT_ID": "synthetic-upstream-client",
            "GITCODE_OAUTH_CLIENT_SECRET": secrets.token_urlsafe(32),
            "GITCODE_MCP_OAUTH_CLIENT_ID": "synthetic-downstream-client",
            "GITCODE_MCP_OAUTH_CLIENT_SECRET": secrets.token_urlsafe(32),
            "GITCODE_MCP_OAUTH_REDIRECT_URIS": "https://client.example.test/callback",
            "GITCODE_MCP_OAUTH_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        },
    }
    provider = provider_for(manifest, directory)
    try:
        deadline = time.time() + 86400
        grant = {
            "client_id": provider.config.client_id,
            "subject": "synthetic-user",
            "login": "synthetic-user",
            "resource": provider.config.resource_url,
            "scopes": ["gitcode:read", "gitcode:write"],
            "expires_at": deadline,
            "upstream": {
                "access_token": manifest["upstream_access"],
                "refresh_token": secrets.token_urlsafe(32),
                "expires_at": deadline,
                "scope": "all_user all_projects",
            },
        }
        code = secrets.token_urlsafe(32)
        provider.store.put("grant", manifest["grant_id"], grant, deadline)
        provider.store.put(
            "code",
            code,
            {key: grant[key] for key in ("client_id", "subject", "resource", "scopes")}
            | {
                "grant_id": manifest["grant_id"],
                "expires_at": time.time() + 120,
                "code_challenge": "a" * 43,
                "redirect_uri": provider.config.redirect_uris[0],
                "redirect_uri_provided_explicitly": True,
            },
            time.time() + 120,
        )
        authorization = await provider.load_authorization_code(provider.client, code)
        assert authorization is not None
        tokens = await provider.exchange_authorization_code(provider.client, authorization)
        manifest.update(access_token=tokens.access_token, refresh_token=tokens.refresh_token)
        assert await provider.load_access_token(tokens.access_token) is not None
    finally:
        await provider.aclose()
    manifest["marker_digest"] = store_format(directory, manifest)
    with (directory / "synthetic-fixture.json").open("x", encoding="utf-8") as stream:
        os.chmod(stream.fileno(), 0o600)
        json.dump(manifest, stream)
    print("Legacy source generated and closed a synthetic encrypted OAuth fixture")


async def verify(directory: Path) -> None:
    manifest = json.loads((directory / "synthetic-fixture.json").read_text(encoding="utf-8"))
    assert manifest["fixture_format"] == FIXTURE_FORMAT and manifest["legacy_sha"] == LEGACY_SHA
    assert store_format(directory, manifest) == manifest["marker_digest"]
    provider = provider_for(manifest, directory)
    try:
        access = await provider.load_access_token(manifest["access_token"])
        assert access is not None and access.grant_id == manifest["grant_id"]
        assert access.client_id == provider.config.client_id
        assert access.resource == provider.config.resource_url
        assert access.scopes == ["gitcode:read", "gitcode:write"]
        assert await provider.upstream_access_token(access) == manifest["upstream_access"]
        refresh = await provider.load_refresh_token(provider.client, manifest["refresh_token"])
        assert refresh is not None and refresh.grant_id == access.grant_id
        rotated = await provider.exchange_refresh_token(provider.client, refresh, access.scopes)
        assert rotated.access_token != manifest["access_token"]
        assert rotated.refresh_token and rotated.refresh_token != manifest["refresh_token"]
        assert provider.store.get("refresh", manifest["refresh_token"]) is None
        assert provider.store.get("used_refresh", manifest["refresh_token"]) is not None
        assert await provider.load_access_token(rotated.access_token) is not None
    finally:
        await provider.aclose()
    assert store_format(directory, manifest) == manifest["marker_digest"]
    # A second sequential open proves rotation persisted, not merely an in-memory cache.
    provider = provider_for(manifest, directory)
    try:
        assert await provider.load_access_token(manifest["access_token"]) is not None
        assert await provider.load_access_token(rotated.access_token) is not None
        assert await provider.load_refresh_token(provider.client, rotated.refresh_token) is not None
        # Replay of the old refresh must still revoke the entire grant after migration.
        assert await provider.load_refresh_token(provider.client, manifest["refresh_token"]) is None
        assert await provider.load_access_token(rotated.access_token) is None
        assert await provider.load_access_token(manifest["access_token"]) is None
    finally:
        await provider.aclose()
    print(
        "Legacy-to-new OAuth: access, refresh rotation, restart, replay rejection and v1 format passed"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "seed", "verify", "_stdio"))
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    isolate_process()
    installed_metadata(legacy=args.mode == "seed")
    if args.mode == "seed":
        assert VERSION == LEGACY_VERSION
    if args.mode == "_stdio":
        entry = next(
            entry
            for entry in importlib.metadata.distribution(PACKAGE).entry_points
            if entry.group == "console_scripts" and entry.name == "gitcode-mcp"
        )
        arguments = ["--read-only"] if args.argument == "1" else []
        raise SystemExit(entry.load()(arguments))
    if args.mode == "smoke":
        smoke()
    else:
        if args.argument is None:
            parser.error("seed and verify require a disposable fixture directory")
        directory = Path(args.argument).absolute()
        assert not directory.is_symlink()
        import anyio

        anyio.run(seed if args.mode == "seed" else verify, directory)


if __name__ == "__main__":
    main()
