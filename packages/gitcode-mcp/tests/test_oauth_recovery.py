"""Rotation recovery and per-grant concurrency use only synthetic encrypted state."""

import time
from dataclasses import replace
from unittest.mock import AsyncMock

import anyio
import pytest
from cryptography.fernet import Fernet

from gitcode_mcp.api import GitCodeError
from gitcode_mcp.config import Settings
from gitcode_mcp.oauth import GitCodeOAuthProvider
from gitcode_mcp.oauth_upstream import GitCodeIdentity, OAuthUpstreamError, UpstreamTokens


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def provider(tmp_path):
    settings = Settings.from_env(
        {
            "GITCODE_MCP_AUTH_MODE": "oauth",
            "GITCODE_MCP_PUBLIC_URL": "https://mcp.example.test",
            "GITCODE_OAUTH_CLIENT_ID": "upstream-app",
            "GITCODE_OAUTH_CLIENT_SECRET": "synthetic-upstream-secret",
            "GITCODE_MCP_OAUTH_CLIENT_ID": "client",
            "GITCODE_MCP_OAUTH_CLIENT_SECRET": "synthetic-client-secret-" * 2,
            "GITCODE_MCP_OAUTH_REDIRECT_URIS": "https://chatgpt.com/connector/oauth/callback",
            "GITCODE_MCP_OAUTH_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GITCODE_MCP_OAUTH_DATABASE": str(tmp_path / "oauth.sqlite3"),
        }
    )
    upstream = AsyncMock()
    upstream.refresh.return_value = UpstreamTokens(
        "new-access", "new-refresh", time.time() + 3600, "all_user all_projects"
    )
    upstream.user.return_value = GitCodeIdentity("subject", "login")
    value = GitCodeOAuthProvider(settings, upstream=upstream)
    yield value
    await value.aclose()


async def grant(provider, grant_id="grant-a", *, expired=True):
    expiry = time.time() + 3600
    record = {
        "client_id": provider.config.client_id,
        "resource": provider.config.resource_url,
        "subject": "subject",
        "scopes": ["gitcode:read"],
        "expires_at": expiry,
        "upstream": {
            "access_token": f"access-{grant_id}",
            "refresh_token": "old-refresh",
            "expires_at": time.time() - 1 if expired else expiry,
            "scope": "all_user all_projects",
        },
    }
    with provider.store.transaction() as tx:
        tx.put("grant", grant_id, record, expiry)
        tokens = provider._issue(tx, grant_id, record, ["gitcode:read"])
    return await provider.load_access_token(tokens.access_token)


@pytest.mark.anyio
async def test_rotated_credentials_survive_identity_failure_and_restart(provider):
    token = await grant(provider)
    provider.upstream.user.side_effect = OAuthUpstreamError("timeout")
    with pytest.raises(GitCodeError, match="temporarily unavailable"):
        await provider.upstream_access_token(token)
    saved = provider.store.get("grant", token.grant_id)
    assert saved["pending_upstream"]["refresh_token"] == "new-refresh"
    raw = provider.store.path.read_bytes()
    assert b"new-access" not in raw and b"new-refresh" not in raw
    provider.store.close()
    # A fresh provider must resume identity verification, never redeem old-refresh.
    upstream = AsyncMock()
    upstream.user.return_value = GitCodeIdentity("subject", "login")
    restarted = GitCodeOAuthProvider(provider.settings, upstream=upstream)
    try:
        assert await restarted.upstream_access_token(token) == "new-access"
        upstream.refresh.assert_not_awaited()
        upstream.user.assert_awaited_once_with("new-access")
        assert "pending_upstream" not in restarted.store.get("grant", token.grant_id)
    finally:
        await restarted.aclose()


@pytest.mark.anyio
async def test_pending_identity_mismatch_revokes_without_releasing_token(provider):
    token = await grant(provider)
    provider.upstream.user.side_effect = [
        OAuthUpstreamError("timeout"),
        GitCodeIdentity("other", "other"),
    ]
    with pytest.raises(GitCodeError):
        await provider.upstream_access_token(token)
    with pytest.raises(GitCodeError, match="Reconnect"):
        await provider.upstream_access_token(token)
    assert provider.store.get("grant", token.grant_id) is None
    provider.upstream.refresh.assert_awaited_once_with("old-refresh")


@pytest.mark.anyio
async def test_slow_refresh_does_not_block_other_grants(provider):
    a = await grant(provider)
    b = await grant(provider, "grant-b", expired=False)
    started, release = anyio.Event(), anyio.Event()
    refreshed = provider.upstream.refresh.return_value

    async def slow_refresh(_):
        started.set()
        await release.wait()
        return refreshed

    provider.upstream.refresh.side_effect = slow_refresh
    async with anyio.create_task_group() as group:
        group.start_soon(provider.upstream_access_token, a)
        await started.wait()
        try:
            with anyio.fail_after(0.5):
                assert await provider.upstream_access_token(b) == "access-grant-b"
        finally:
            release.set()
    assert provider._refresh_locks == {}


@pytest.mark.anyio
async def test_same_grant_wait_is_bounded_without_cancelling_holder(provider):
    token = await grant(provider)
    started, release = anyio.Event(), anyio.Event()
    refreshed = provider.upstream.refresh.return_value
    provider.settings = replace(provider.settings, timeout=0.02)

    async def slow_refresh(_):
        started.set()
        await release.wait()
        return refreshed

    provider.upstream.refresh.side_effect = slow_refresh
    async with anyio.create_task_group() as group:
        group.start_soon(provider.upstream_access_token, token)
        await started.wait()
        try:
            with pytest.raises(GitCodeError, match="busy"), anyio.fail_after(0.5):
                await provider.upstream_access_token(token)
            assert len(provider._refresh_locks) == 1
        finally:
            release.set()
    assert await provider.upstream_access_token(token) == "new-access"
    provider.upstream.refresh.assert_awaited_once()
    assert provider._refresh_locks == {}


@pytest.mark.anyio
async def test_unknown_exchange_outcome_never_redeems_old_refresh_again(provider):
    token = await grant(provider)
    provider.upstream.refresh.side_effect = OAuthUpstreamError("timeout")
    with pytest.raises(GitCodeError):
        await provider.upstream_access_token(token)
    with pytest.raises(GitCodeError, match="Reconnect"):
        await provider.upstream_access_token(token)
    provider.upstream.refresh.assert_awaited_once()


@pytest.mark.anyio
async def test_revocation_during_identity_lookup_does_not_resurrect_grant(provider):
    token = await grant(provider)

    async def revoke(_):
        await provider.revoke_token(token)
        return GitCodeIdentity("subject", "login")

    provider.upstream.user.side_effect = revoke
    with pytest.raises(GitCodeError, match="Reconnect"):
        await provider.upstream_access_token(token)
    assert provider.store.get("grant", token.grant_id) is None


@pytest.mark.anyio
async def test_cancelled_identity_lookup_retains_pending_credentials_and_releases_lock(provider):
    token = await grant(provider)
    started = anyio.Event()

    async def slow_user(_):
        started.set()
        await anyio.sleep_forever()

    provider.upstream.user.side_effect = slow_user
    async with anyio.create_task_group() as group:
        group.start_soon(provider.upstream_access_token, token)
        await started.wait()
        group.cancel_scope.cancel()
    assert provider._refresh_locks == {}
    assert (
        provider.store.get("grant", token.grant_id)["pending_upstream"]["access_token"]
        == "new-access"
    )
    provider.upstream.user.side_effect = None
    assert await provider.upstream_access_token(token) == "new-access"
    provider.upstream.refresh.assert_awaited_once()
