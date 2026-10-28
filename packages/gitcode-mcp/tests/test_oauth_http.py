import base64
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from gitcode_mcp.api import GitCodeAPI
from gitcode_mcp.config import ConfigurationError, Settings
from gitcode_mcp.oauth import GitCodeOAuthProvider
from gitcode_mcp.oauth_upstream import GitCodeOAuthUpstream
from gitcode_mcp.server import create_http_app, create_server

PUBLIC = "https://mcp.example.test"
RESOURCE = PUBLIC + "/mcp"
REDIRECT = "https://chatgpt.com/connector/oauth/test-callback"
CLIENT_SECRET = "downstream-client-secret-" * 2
VERIFIER = "a" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
)


class Harness:
    def __init__(self, tmp_path, *, env=None, database=None):
        self.env = env or {
            "GITCODE_MCP_AUTH_MODE": "oauth",
            "GITCODE_MCP_PUBLIC_URL": PUBLIC,
            "GITCODE_OAUTH_CLIENT_ID": "upstream-app",
            "GITCODE_OAUTH_CLIENT_SECRET": "upstream-secret-never-public",
            "GITCODE_MCP_OAUTH_CLIENT_ID": "chatgpt-client",
            "GITCODE_MCP_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
            "GITCODE_MCP_OAUTH_REDIRECT_URIS": REDIRECT,
            "GITCODE_MCP_OAUTH_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GITCODE_MCP_OAUTH_DATABASE": str(database or tmp_path / "oauth.sqlite3"),
            "GITCODE_MCP_ALLOWED_REPOS": "allowed/repo",
        }
        self.settings = Settings.from_env(self.env)
        self.upstream_requests = []
        self.api_requests = []
        self.refresh_error = False
        self.api_status = 200

        async def upstream(request):
            self.upstream_requests.append(request)
            if request.url.path == "/oauth/token":
                if request.url.params["grant_type"] == "refresh_token":
                    await anyio.sleep(0.02)
                    if self.refresh_error:
                        return httpx.Response(
                            400, json={"error": "invalid_grant", "secret": "upstream-body-secret"}
                        )
                    user = request.url.params["refresh_token"].removeprefix("gitcode-refresh-")
                    token = "gitcode-access-" + user + "-rotated"
                else:
                    user = request.url.params["code"]
                    token = "gitcode-access-" + user
                return httpx.Response(
                    200,
                    json={
                        "access_token": token,
                        "refresh_token": "gitcode-refresh-" + user,
                        "expires_in": 3600,
                        "scope": "all_user all_projects",
                    },
                )
            assert request.url == "https://api.gitcode.com/api/v5/user"
            user = (
                request.headers["authorization"]
                .removeprefix("Bearer gitcode-access-")
                .removesuffix("-rotated")
            )
            return httpx.Response(200, json={"id": user, "login": "login-" + user})

        def api(request):
            self.api_requests.append(request)
            if self.api_status != 200:
                return httpx.Response(
                    self.api_status, json={"message": "sensitive upstream failure"}
                )
            user = (
                request.headers["authorization"]
                .removeprefix("Bearer gitcode-access-")
                .removesuffix("-rotated")
            )
            if "/contents/" in request.url.path and request.method in {"POST", "PUT", "DELETE"}:
                return httpx.Response(
                    200,
                    json={"commit": {"sha": "a" * 40}, "content": {"sha": "b" * 40}},
                )
            return httpx.Response(200, json={"id": user, "full_name": "allowed/repo"})

        self.upstream = GitCodeOAuthUpstream(
            self.settings.oauth.gitcode_client_id,
            self.settings.oauth.gitcode_client_secret,
            self.settings.oauth.callback_url,
            transport=httpx.MockTransport(upstream),
        )
        self.provider = GitCodeOAuthProvider(self.settings, upstream=self.upstream)
        self.shared_api = GitCodeAPI(
            "fallback-PAT-must-never-be-used", transport=httpx.MockTransport(api)
        )
        server = create_server(
            self.settings,
            api=self.shared_api,
            oauth_provider=self.provider,
            api_factory=lambda token: GitCodeAPI(token, transport=httpx.MockTransport(api)),
        )
        self.app = create_http_app(server, self.settings, "0.0.0.0", oauth_provider=self.provider)
        self.client = TestClient(self.app, base_url=PUBLIC, follow_redirects=False)

    def close(self):
        self.client.close()
        anyio.run(self.provider.aclose)
        self.shared_api.close()


@pytest.fixture
def harness(tmp_path):
    value = Harness(tmp_path)
    with value.client:
        yield value
    value.close()


def begin(client, *, scope="gitcode:read gitcode:write", **overrides):
    params = {
        "client_id": "chatgpt-client",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": scope,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
        "state": "chatgpt-state",
        **overrides,
    }
    response = client.get("/authorize", params=params)
    assert response.status_code == 302, response.text
    assert response.headers["location"].startswith(PUBLIC + "/oauth/start?")
    start = client.get(response.headers["location"])
    assert start.status_code == 303, start.text
    parsed = urlsplit(start.headers["location"])
    assert parsed.scheme == "https" and parsed.netloc == "gitcode.com"
    query = parse_qs(parsed.query)
    assert query["redirect_uri"] == [PUBLIC + "/oauth/gitcode/callback"]
    assert query["prompt"] == ["consent"]
    assert query["state"] != ["chatgpt-state"]
    assert "Secure" in start.headers["set-cookie"] and "HttpOnly" in start.headers["set-cookie"]
    return query["state"][0]


def callback(client, state, user="user-a"):
    response = client.get("/oauth/gitcode/callback", params={"state": state, "code": user})
    assert response.status_code == 303, response.text
    page = client.get(response.headers["location"])
    assert page.status_code == 200, page.text
    assert "login-" + user in page.text
    assert "gitcode-access-" not in page.text
    return {
        name: re.search(r'name="' + name + r'" value="([^"]+)"', page.text)[1]
        for name in ("flow", "csrf")
    }


def consent(client, fields, decision="allow"):
    response = client.post(
        "/oauth/consent", data={**fields, "decision": decision}, headers={"Origin": PUBLIC}
    )
    assert response.status_code == 303, response.text
    parsed = urlsplit(response.headers["location"])
    assert parsed.netloc == "chatgpt.com"
    query = parse_qs(parsed.query)
    assert query["state"] == ["chatgpt-state"]
    return query


def token_request(client, *, code=None, refresh=None, **overrides):
    fields = {
        "client_id": "chatgpt-client",
        "client_secret": CLIENT_SECRET,
        "resource": RESOURCE,
    }
    if code is not None:
        fields.update(
            grant_type="authorization_code",
            code=code,
            redirect_uri=REDIRECT,
            code_verifier=VERIFIER,
        )
    else:
        fields.update(grant_type="refresh_token", refresh_token=refresh)
    return client.post("/token", data={**fields, **overrides})


def connect(harness, user="user-a", scope="gitcode:read gitcode:write"):
    client = harness.client
    state = begin(client, scope=scope)
    fields = callback(client, state, user)
    code = consent(client, fields)["code"][0]
    response = token_request(client, code=code)
    assert response.status_code == 200, response.text
    assert "gitcode-access" not in response.text and "gitcode-refresh" not in response.text
    return response.json()


def rpc(client, token, method="tools/list", params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post(
        "/mcp",
        json=payload,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
    )


def repository(client, token):
    return rpc(
        client,
        token,
        "tools/call",
        {
            "name": "gitcode_get_repository",
            "arguments": {"owner": "allowed", "repo": "repo"},
        },
    )


def test_complete_http_oauth_and_mcp_flow(harness):
    client = harness.client
    metadata = client.get("/.well-known/oauth-authorization-server").json()
    assert metadata["authorization_endpoint"] == PUBLIC + "/authorize"
    assert metadata["token_endpoint_auth_methods_supported"] == ["client_secret_post"]
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert "registration_endpoint" not in metadata
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == RESOURCE
    unauthenticated = client.post("/mcp", json={})
    assert unauthenticated.status_code == 401
    assert (
        "/.well-known/oauth-protected-resource/mcp" in unauthenticated.headers["www-authenticate"]
    )
    tokens = connect(harness)
    initialized = rpc(
        client,
        tokens["access_token"],
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "codeasier-gitcode"
    notified = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={
            "Authorization": "Bearer " + tokens["access_token"],
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
    )
    assert notified.status_code == 202
    tools = rpc(client, tokens["access_token"]).json()["result"]["tools"]
    assert len(tools) == 31
    assert all(tool["_meta"]["securitySchemes"][0]["type"] == "oauth2" for tool in tools)
    result = repository(client, tokens["access_token"])
    assert result.json()["result"]["structuredContent"]["data"]["id"] == "user-a"
    assert harness.api_requests[-1].headers["authorization"] == "Bearer gitcode-access-user-a"


def test_pkce_resource_redirect_and_authorization_code_replay(harness):
    client = harness.client
    code = consent(client, callback(client, begin(client)))["code"][0]
    assert (
        token_request(client, code=code, resource="https://other.test/mcp").json()["error"]
        == "invalid_target"
    )
    assert (
        token_request(client, code=code, redirect_uri="https://attacker.test/callback").status_code
        == 400
    )
    assert (
        token_request(client, code=code, code_verifier="b" * 43).json()["error"] == "invalid_grant"
    )
    assert token_request(client, code=code, client_secret="wrong").status_code == 401
    response = token_request(client, code=code)
    assert response.status_code == 200
    assert token_request(client, code=code).json()["error"] == "invalid_grant"
    assert repository(client, response.json()["access_token"]).status_code == 200


def test_callback_and_consent_are_bound_to_browser_and_not_replayable(harness):
    client = harness.client
    state = begin(client)
    # A second TestClient without a lifespan shares the app, not browser cookies.
    other = TestClient(harness.app, base_url=PUBLIC, follow_redirects=False)
    denied = other.get("/oauth/gitcode/callback", params={"code": "user-a", "state": state})
    other.close()
    assert denied.status_code == 400
    assert harness.upstream_requests == []
    fields = callback(client, state)
    assert (
        client.get("/oauth/gitcode/callback", params={"code": "user-a", "state": state}).status_code
        == 400
    )
    assert client.post("/oauth/consent", data={**fields, "decision": "allow"}).status_code == 403
    assert (
        client.post(
            "/oauth/consent",
            data={**fields, "csrf": "forged", "decision": "allow"},
            headers={"Origin": PUBLIC},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/oauth/consent",
            data={**fields, "csrf": "非 ASCII", "decision": "allow"},
            headers={"Origin": PUBLIC},
        ).status_code
        == 403
    )
    code = consent(client, fields)["code"][0]
    assert (
        client.post(
            "/oauth/consent", data={**fields, "decision": "allow"}, headers={"Origin": PUBLIC}
        ).status_code
        == 403
    )
    assert token_request(client, code=code).status_code == 200


def test_consent_denial_and_account_allowlist(harness):
    client = harness.client
    denied = consent(client, callback(client, begin(client)), decision="deny")
    assert denied["error"] == ["access_denied"] and "code" not in denied
    harness.provider.config = replace(harness.provider.config, allowed_user_ids=("user-a",))
    state = begin(client)
    response = client.get("/oauth/gitcode/callback", params={"state": state, "code": "user-b"})
    assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == ["access_denied"]


def test_two_accounts_and_read_write_scopes_are_isolated_under_concurrency(harness):
    alice = connect(harness, "user-a")
    bob = connect(harness, "user-b", scope="gitcode:read")
    assert len(rpc(harness.client, bob["access_token"]).json()["result"]["tools"]) == 19
    assert len(rpc(harness.client, alice["access_token"]).json()["result"]["tools"]) == 31
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda token: repository(harness.client, token),
                [alice["access_token"], bob["access_token"]],
            )
        )
    assert [r.json()["result"]["structuredContent"]["data"]["id"] for r in results] == [
        "user-a",
        "user-b",
    ]
    before = len(harness.api_requests)
    write = rpc(
        harness.client,
        bob["access_token"],
        "tools/call",
        {
            "name": "gitcode_create_issue",
            "arguments": {"owner": "allowed", "repo": "repo", "title": "Must not write"},
        },
    )
    assert write.json()["result"]["isError"]
    outside = rpc(
        harness.client,
        alice["access_token"],
        "tools/call",
        {
            "name": "gitcode_get_repository",
            "arguments": {"owner": "outside", "repo": "repo"},
        },
    )
    assert outside.json()["result"]["isError"]
    assert len(harness.api_requests) == before
    assert rpc(harness.client, "fallback-PAT-must-never-be-used").status_code == 401


def test_file_publication_uses_each_oauth_identity_and_enforces_scope_and_allowlist(harness):
    alice = connect(harness, "writer-a")
    bob = connect(harness, "writer-b")
    reader = connect(harness, "reader", scope="gitcode:read")
    arguments = {
        "owner": "allowed",
        "repo": "repo",
        "path": "src/example.py",
        "branch": "feat/oauth-publication",
        "message": "Publish the requested code change",
        "content": "print('hello')\n",
    }
    catalog = rpc(harness.client, alice["access_token"]).json()["result"]["tools"]
    file_tools = {
        tool["name"]: tool
        for tool in catalog
        if tool["name"] in {"gitcode_create_file", "gitcode_update_file", "gitcode_delete_file"}
    }
    assert len(file_tools) == 3
    for tool in file_tools.values():
        assert tool["_meta"]["securitySchemes"] == [
            {"type": "oauth2", "scopes": ["gitcode:read", "gitcode:write"]}
        ]
        assert not tool["annotations"]["readOnlyHint"]
        assert not tool["annotations"]["idempotentHint"]
    for identity in (alice, bob):
        response = rpc(
            harness.client,
            identity["access_token"],
            "tools/call",
            {"name": "gitcode_create_file", "arguments": arguments},
        )
        result = response.json()["result"]
        assert not result.get("isError")
        assert result["structuredContent"]["data"]["commit_sha"] == "a" * 40
        assert "gitcode-access-" not in response.text
    assert [request.headers["authorization"] for request in harness.api_requests] == [
        "Bearer gitcode-access-writer-a",
        "Bearer gitcode-access-writer-b",
    ]
    before = len(harness.api_requests)
    for tool in file_tools:
        payload = dict(arguments)
        if tool != "gitcode_create_file":
            payload["sha"] = "c" * 40
        if tool == "gitcode_delete_file":
            payload.pop("content")
        denied = rpc(
            harness.client,
            reader["access_token"],
            "tools/call",
            {"name": tool, "arguments": payload},
        )
        assert denied.json()["result"]["isError"]
        outside = rpc(
            harness.client,
            alice["access_token"],
            "tools/call",
            {"name": tool, "arguments": {**payload, "owner": "outside"}},
        )
        assert outside.json()["result"]["isError"]
    assert len(harness.api_requests) == before


def test_file_publication_http_budget_accepts_escaped_limit_and_rejects_oversized_body(harness):
    tokens = connect(harness)
    # A valid maximum-size text file may occupy six times its size in JSON.
    content = "\x01" * (256 * 1024)
    arguments = {
        "owner": "allowed",
        "repo": "repo",
        "path": "data/control.txt",
        "branch": "feat/body-budget",
        "message": "Add a bounded file",
        "content": content,
    }
    assert len(json.dumps(arguments).encode()) > 1_048_576
    response = rpc(
        harness.client,
        tokens["access_token"],
        "tools/call",
        {"name": "gitcode_create_file", "arguments": arguments},
    )
    assert response.status_code == 200
    assert not response.json()["result"].get("isError")
    assert len(harness.api_requests) == 1
    payload = json.loads(harness.api_requests[0].content)
    assert base64.b64decode(payload["content"]) == content.encode()
    oversized = rpc(
        harness.client,
        tokens["access_token"],
        "tools/call",
        {"name": "gitcode_create_file", "arguments": {**arguments, "content": "a" * 2_097_152}},
    )
    assert oversized.status_code == 413
    assert len(harness.api_requests) == 1


@pytest.mark.parametrize("scope", ["gitcode:read", "gitcode:read gitcode:write"])
def test_consent_describes_file_publication_only_for_write_scope(harness, scope):
    state = begin(harness.client, scope=scope)
    response = harness.client.get(
        "/oauth/gitcode/callback", params={"state": state, "code": "user-a"}
    )
    page = harness.client.get(response.headers["location"])
    assert page.status_code == 200
    assert ("publish code commits" in page.text) == ("gitcode:write" in scope)
    assert ("create, replace and delete repository files" in page.text) == (
        "gitcode:write" in scope
    )


def test_refresh_rotation_replay_and_revocation(harness):
    first = connect(harness)
    client = harness.client
    assert (
        token_request(
            client, refresh=first["refresh_token"], resource="https://wrong.test/mcp"
        ).status_code
        == 400
    )
    second_response = token_request(client, refresh=first["refresh_token"], scope="gitcode:read")
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert len(rpc(client, second["access_token"]).json()["result"]["tools"]) == 19
    assert token_request(client, refresh=first["refresh_token"]).json()["error"] == "invalid_grant"
    assert rpc(client, second["access_token"]).status_code == 401
    assert token_request(client, refresh=second["refresh_token"]).json()["error"] == "invalid_grant"
    third = connect(harness, "user-b")
    revoked = client.post(
        "/revoke",
        data={
            "client_id": "chatgpt-client",
            "client_secret": CLIENT_SECRET,
            "token": third["access_token"],
        },
    )
    assert revoked.status_code == 200
    assert rpc(client, third["access_token"]).status_code == 401
    assert token_request(client, refresh=third["refresh_token"]).status_code == 400


def test_upstream_refresh_is_serialized_and_bad_grant_does_not_fall_back(harness):
    tokens = connect(harness)
    record = harness.provider.store.get("access", tokens["access_token"])
    grant = harness.provider.store.get("grant", record["grant_id"])
    grant["upstream"]["expires_at"] = time.time() - 1
    harness.provider.store.put("grant", record["grant_id"], grant, grant["expires_at"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: repository(harness.client, tokens["access_token"]), range(2))
        )
    assert all(
        result.status_code == 200 and not result.json()["result"].get("isError")
        for result in results
    )
    refreshes = [
        r for r in harness.upstream_requests if r.url.params.get("grant_type") == "refresh_token"
    ]
    assert len(refreshes) == 1
    assert all(
        r.headers["authorization"] == "Bearer gitcode-access-user-a-rotated"
        for r in harness.api_requests
    )
    grant = harness.provider.store.get("grant", record["grant_id"])
    grant["upstream"]["expires_at"] = time.time() - 1
    harness.provider.store.put("grant", record["grant_id"], grant, grant["expires_at"])
    harness.refresh_error = True
    before = len(harness.api_requests)
    failure = repository(harness.client, tokens["access_token"])
    assert failure.json()["result"]["isError"]
    assert "mcp/www_authenticate" in failure.json()["result"]["_meta"]
    assert "upstream-body-secret" not in failure.text
    assert len(harness.api_requests) == before
    assert rpc(harness.client, tokens["access_token"]).status_code == 401


def test_expired_access_and_revoked_gitcode_credential_require_authentication(harness):
    first = connect(harness)
    record = harness.provider.store.get("access", first["access_token"])
    record["expires_at"] = time.time() - 1
    harness.provider.store.put("access", first["access_token"], record, record["expires_at"])
    assert rpc(harness.client, first["access_token"]).status_code == 401
    new = token_request(harness.client, refresh=first["refresh_token"]).json()
    harness.api_status = 401
    failed = repository(harness.client, new["access_token"])
    assert failed.json()["result"]["isError"]
    assert "mcp/www_authenticate" in failed.json()["result"]["_meta"]
    assert rpc(harness.client, new["access_token"]).status_code == 401


def test_restart_preserves_grants_and_scopes(tmp_path):
    original = Harness(tmp_path)
    with original.client:
        tokens = connect(original)
    original.close()
    restarted = Harness(tmp_path, env=original.env)
    try:
        with restarted.client:
            assert (
                repository(restarted.client, tokens["access_token"]).json()["result"][
                    "structuredContent"
                ]["data"]["id"]
                == "user-a"
            )
            assert (
                token_request(restarted.client, refresh=tokens["refresh_token"]).status_code == 200
            )
    finally:
        restarted.close()


def test_public_boundaries_and_resource_parameters(harness):
    client = harness.client
    for path in ("/.well-known/oauth-authorization-server", "/authorize", "/oauth/start"):
        assert client.get(path, headers={"Host": "attacker.test"}).status_code == 421
        assert client.get(path, headers={"Origin": "https://attacker.test"}).status_code == 403
    response = client.get(
        "/authorize",
        params={
            "client_id": "chatgpt-client",
            "redirect_uri": "https://attacker.test/callback",
            "response_type": "code",
            "code_challenge": CHALLENGE,
        },
    )
    assert response.status_code == 400 and "location" not in response.headers
    assert client.get("/authorize?resource=x&resource=y").status_code == 400
    assert client.get("/oauth/start?client_secret=hidden").status_code == 400
    assert (
        client.post(
            "/token",
            content="resource=a&resource=b",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/token",
            content="a" * 16385,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 413
    )
    assert client.post("/token", json={}).status_code == 415
    assert (
        client.get(
            "/oauth/start",
            headers=[("Authorization", "Bearer first"), ("Authorization", "Bearer second")],
        ).status_code
        == 400
    )


def test_empty_redirect_allowlist_bootstraps_discovery_only(tmp_path):
    seed = Harness(tmp_path)
    env = {**seed.env, "GITCODE_MCP_OAUTH_REDIRECT_URIS": ""}
    seed.close()
    value = Harness(tmp_path, env=env)
    try:
        with value.client:
            assert value.client.get("/.well-known/oauth-authorization-server").status_code == 200
            response = value.client.get(
                "/authorize",
                params={
                    "client_id": "chatgpt-client",
                    "redirect_uri": REDIRECT,
                    "response_type": "code",
                    "code_challenge": CHALLENGE,
                    "code_challenge_method": "S256",
                    "resource": RESOURCE,
                },
            )
            assert response.status_code == 400
            assert "location" not in response.headers
    finally:
        value.close()


def test_oauth_provider_is_mandatory_in_server_and_transport(harness):
    with pytest.raises(ConfigurationError):
        create_server(harness.settings, api=harness.shared_api)
    plain = create_server(Settings(), api=harness.shared_api)
    with pytest.raises(ConfigurationError):
        create_http_app(plain, harness.settings)


def test_concurrent_code_exchange_only_issues_once(harness):
    code = consent(harness.client, callback(harness.client, begin(harness.client)))["code"][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: token_request(harness.client, code=code), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 400]


def test_concurrent_refresh_replay_revokes_the_token_family(harness):
    tokens = connect(harness)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: token_request(harness.client, refresh=tokens["refresh_token"]), range(2)
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 400]
    issued = next(response.json() for response in responses if response.status_code == 200)
    assert repository(harness.client, issued["access_token"]).status_code == 401


def test_public_origin_normalization_matches_oauth_discovery(tmp_path):
    seed = Harness(tmp_path)
    env = {**seed.env, "GITCODE_MCP_PUBLIC_URL": "https://MCP.EXAMPLE.TEST:443/"}
    seed.close()
    value = Harness(tmp_path, env=env)
    try:
        with value.client:
            assert value.settings.oauth.public_url == PUBLIC
            assert (
                value.client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"]
                == RESOURCE
            )
            assert repository(value.client, connect(value)["access_token"]).status_code == 200
    finally:
        value.close()
