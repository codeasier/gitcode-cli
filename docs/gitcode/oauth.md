# GitCode OAuth for a public MCP server

OAuth mode connects ChatGPT to a public HTTPS MCP endpoint and lets each connection authorize its own GitCode account. It does not require a tunnel or a GitCode PAT on the server.

The service has two OAuth roles:

- **Towards GitCode:** it is a confidential client of your GitCode OAuth application.
- **Towards ChatGPT:** it is an MCP resource server and OAuth authorization server with one explicitly configured, preregistered confidential client.

These clients have different IDs, secrets and callbacks. GitCode access and refresh tokens stay on the MCP host. ChatGPT receives separate MCP credentials bound to the authorized connection, client, resource and scopes.

> Already running this service from `codex-codeasier`? Use [migration and rollback](migration.md), not the new-install credential generation below. The source move does not change the public URL, OAuth clients, environment names, database schema, Fernet key or store marker, and does not itself require reauthorization.

## 1. Choose the public origin

Use a stable HTTPS origin, for example `https://mcp.example.com`. `GITCODE_MCP_PUBLIC_URL` accepts an origin only, without a path, query or fragment.

For that example:

| Purpose | URL |
| --- | --- |
| ChatGPT Server URL / protected MCP resource | `https://mcp.example.com/mcp` |
| GitCode application's callback | `https://mcp.example.com/oauth/gitcode/callback` |
| MCP OAuth authorization endpoint | `https://mcp.example.com/authorize` |
| MCP OAuth token endpoint | `https://mcp.example.com/token` |
| MCP OAuth revocation endpoint | `https://mcp.example.com/revoke` |

The server also serves OAuth discovery metadata and its own login/consent routes. Forward the whole dedicated virtual host to the application, including `/.well-known/`, `/oauth/start`, `/oauth/gitcode/callback` and `/oauth/consent`. Do not place a separate browser-login redirect or static bearer requirement in front of discovery.

The configured public origin determines OAuth URLs. Preserve it across restarts; do not generate an issuer or callback from an untrusted incoming Host or forwarded header.

## 2. Register the upstream GitCode application

In GitCode, open **Personal settings → OAuth applications** and create an application:

1. Set its homepage to your public HTTPS origin.
2. Set its callback to the exact `/oauth/gitcode/callback` URL above.
3. Select the GitCode permissions needed for the repositories, issues and PRs you intend to manage.
4. Store the generated Client ID as `GITCODE_OAUTH_CLIENT_ID` and its secret as `GITCODE_OAUTH_CLIENT_SECRET`.

The GitCode callback belongs to this server. It is different from the ChatGPT callback configured in the next section.

`GITCODE_OAUTH_SCOPES` is an optional space-separated list. When empty, the server omits the upstream `scope` parameter. GitCode's public OAuth documentation gives scope examples but does not provide a complete current permission mapping; use the permissions offered by your registered application and verify them with that account. Do not substitute GitHub scope names.

GitCode's documented endpoints are `https://gitcode.com/oauth/authorize`, `https://gitcode.com/oauth/token` and `https://api.gitcode.com/api/v5/user`. The adapter keeps `client_secret` in the token request's multipart body, following the parameter table rather than the conflicting URL example. Code and refresh-token exchanges use GitCode's documented query parameters; request URLs and callback queries must not be logged.

References: [GitCode OAuth](https://docs.gitcode.com/docs/apis/oauth/), [token API](https://docs.gitcode.com/docs/apis/post-oauth-token-grant-type-authorization-code-code-code-client-id-client-id-client-secret-client-secret/), and the [GitCode application setup illustrated in Tencent's integration guide](https://adp.tencent.com/zh/document/216860848528707584).

## 3. Configure ChatGPT's client

Create a distinct MCP client ID and a random secret of at least 32 characters:

- `GITCODE_MCP_OAUTH_CLIENT_ID`: the identifier you will enter in ChatGPT.
- `GITCODE_MCP_OAUTH_CLIENT_SECRET`: the independent secret you will enter in ChatGPT.
- `GITCODE_MCP_OAUTH_REDIRECT_URIS`: the exact HTTPS callback URL shown by ChatGPT's MCP server management page; comma-separate additional callbacks only when explicitly needed.

This release supports preregistration and `client_secret_post`. Dynamic client registration and Client ID Metadata Documents are not enabled. Choose the explicit OAuth client credentials option in ChatGPT and use the MCP client credentials above, not the upstream GitCode application's credentials.

Copy the callback from the actual ChatGPT connection. Do not guess a callback ID or use a wildcard. This server does not advertise RFC 9207 issuer identification, so a new ChatGPT connection can use a callback-specific redirect URL.

For initial setup, leave `GITCODE_MCP_OAUTH_REDIRECT_URIS` empty and start the configured HTTPS service. Discovery works in this bootstrap state, but every authorization callback is rejected. Start creating the ChatGPT connection, obtain the exact callback from its management page, update the allowlist and restart the service before completing account linking. An empty allowlist never means unrestricted redirects.

The MCP scopes are:

| Scope | Permission |
| --- | --- |
| `gitcode:read` | Read GitCode repository, issue and PR data |
| `gitcode:write` | Use write tools when server write mode and GitCode permissions also allow them |

These are this service's scopes, separate from GitCode application scopes. The browser flow first authorizes GitCode, then explicitly asks the user to approve the MCP client and requested scopes. PKCE with `S256` protects the downstream authorization-code exchange.

Official references: [custom MCP connection](https://developers.openai.com/api/docs/guides/custom-mcp-server) and [MCP authentication](https://developers.openai.com/plugins/build/auth).

## 4. Configure persistent state and access

| Variable | Meaning |
| --- | --- |
| `GITCODE_MCP_AUTH_MODE=oauth` | Enable OAuth for Streamable HTTP; the existing default is `bearer` |
| `GITCODE_MCP_PUBLIC_URL` | Fixed public HTTPS origin |
| `GITCODE_OAUTH_CLIENT_ID`, `GITCODE_OAUTH_CLIENT_SECRET` | Upstream GitCode application credentials |
| `GITCODE_OAUTH_SCOPES` | Optional space-separated GitCode scopes |
| `GITCODE_MCP_OAUTH_CLIENT_ID`, `GITCODE_MCP_OAUTH_CLIENT_SECRET` | Preregistered downstream MCP client; its secret must have at least 32 characters |
| `GITCODE_MCP_OAUTH_REDIRECT_URIS` | Comma-separated exact HTTPS callback allowlist; empty permits discovery but rejects authorization |
| `GITCODE_MCP_OAUTH_ENCRYPTION_KEY` | Persistent Fernet key: URL-safe base64 encoding of 32 random bytes |
| `GITCODE_MCP_OAUTH_DATABASE` | Absolute SQLite file path; default `/var/lib/gitcode-mcp/oauth.sqlite3` |
| `GITCODE_MCP_OAUTH_ALLOWED_USER_IDS` | Optional comma-separated stable GitCode user IDs allowed to link |
| `GITCODE_MCP_ALLOWED_REPOS` | Optional comma-separated `owner/repo` allowlist applied to every connection |
| `GITCODE_MCP_READ_ONLY` | Set `true` for initial verification; the OAuth Compose file defaults to `true` |
| `GITCODE_MCP_ALLOWED_HOSTS` | Explicit hosts actually forwarded by the reverse proxy |
| `GITCODE_MCP_ALLOWED_ORIGINS` | Explicit HTTP origins accepted when a request has an Origin header |

OAuth mode rejects simultaneous `GITCODE_TOKEN`, `GC_TOKEN` or `GITCODE_MCP_HTTP_TOKEN` configuration. It never falls back to a process-wide PAT if a connection is missing, expired or invalid.

Each grant uses the GitCode credentials obtained by that grant's own authorization. Leaving `GITCODE_MCP_OAUTH_ALLOWED_USER_IDS` empty permits users who can complete the configured OAuth flow to use their own accounts; it does not give them another user's credentials. Set an explicit stable-ID allowlist for a personal deployment. GitCode IDs can be strings, so copy the actual ID returned for the intended account rather than assuming a numeric ID or substituting its username.

The repository allowlist narrows upstream permissions; it cannot grant access to a repository the authorized GitCode user cannot access. Server write mode and the grant's `gitcode:write` scope are both required for mutations.

MCP access tokens expire after at most 15 minutes. A grant and its downstream refresh capability have a fixed 30-day lifetime; reconnect after that lifetime. Server-side refresh uses the grant's own stored GitCode refresh token.

Upstream rotation is serialized per grant. Another user's valid token is not blocked by a slow refresh; same-grant lock acquisition is bounded by `GITCODE_MCP_TIMEOUT` (30 seconds by default). Rotated credentials are saved encrypted as pending before the identity lookup. A transient lookup failure or cancellation can resume that lookup, including after restart, without reusing the old refresh token. Pending credentials are not released to tools until the stable subject matches; a mismatch revokes the grant. Revocation during refresh is never undone by a late response.

An interrupted or ambiguous token exchange with no saved replacement requires reconnection rather than automatically redeeming the old refresh token again. The refresh intent and pending state are encrypted grant payload fields, without a database schema/key change. Older versions do not understand pending rotation recovery: reverting during a pending/unknown rotation may require that affected connection to reauthorize. Validate upgrade/rollback with synthetic state before deployment.

The SQLite state and encryption key must survive restarts together. Keep the key outside source control and back it up separately from the database. Changing or losing it makes existing encrypted credentials unusable; do not rotate it by simply replacing the value under an existing database. This deployment supports one service process/worker and one persistent database, not multiple replicas sharing a SQLite file.

The store limits pending authorization records to 256 and total persistent records to 10,000. An unauthenticated caller cannot fill the entire store with pending logins; new work is rejected at the smaller limit. The public reverse proxy should also rate-limit authorization starts and token requests as shown in [deployment](deployment.md#configure-https). Do not apply those login limits to ordinary MCP calls.

## 5. Prepare a private environment file

Use an existing secret manager when available. For the Compose example, copy [`oauth.env.example`](../../deploy/gitcode-mcp/oauth.env.example) to an absolute path outside the repository, restrict it to mode `0600`, and fill its non-secret settings plus the GitCode application's credentials using a trusted local editor.

The following optional preparation creates a new file and generates the independent MCP secret and storage key without printing them. Replace the private path and create its parent directory first. It deliberately refuses to overwrite an existing file.

```bash
python3 - <<'PY'
import base64
import os
from pathlib import Path
import secrets

destination = Path("/absolute/path/to/private/gitcode-oauth.env")
template = Path("deploy/gitcode-mcp/oauth.env.example").read_text()
values = {
    "GITCODE_MCP_OAUTH_CLIENT_SECRET": secrets.token_urlsafe(32),
    "GITCODE_MCP_OAUTH_ENCRYPTION_KEY":
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
}
for name, value in values.items():
    template = template.replace(f"{name}=\n", f"{name}={value}\n")
descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as stream:
    stream.write(template)
PY
```

This does not create a GitCode application, register a ChatGPT connection or fill their IDs/callbacks. Complete the application credentials and public settings before startup; the downstream callback allowlist can remain empty for the discovery-only bootstrap above. Do not paste the resulting environment file into chat or include it in diagnostics. Avoid `docker compose config`, `docker inspect` or debug logging that prints resolved credentials.

## 6. Deploy and verify

Follow [public HTTPS deployment](deployment.md#public-https-with-gitcode-oauth), then [connect ChatGPT](connect-dot.md).

The built-in `python -m gitcode_mcp.smoke` starts a **stdio** subprocess. It verifies the local/PAT transport and is not an OAuth, reverse-proxy or public-HTTP acceptance test. Use a real MCP OAuth client against the final HTTPS URL to verify:

1. Public metadata discovery and an OAuth challenge for an unauthenticated MCP request.
2. The authorization-code flow, the GitCode callback, explicit MCP consent and PKCE-protected code exchange.
3. MCP initialization, tool discovery and a read of an allowed repository.
4. Rejection of invalid credentials, disallowed identities, out-of-scope writes and out-of-allowlist repositories.
5. Continued access through token refresh and service restart, with the same database and storage key.
6. The same read through the installed ChatGPT connection.

Keep deployment acceptance read-only. Enable `GITCODE_MCP_READ_ONLY=false` for the intended file publishing or Issue/PR management workflow after the correct account and repository access have been verified. Refresh ChatGPT's tool metadata. If the grant was read-only, reconnect or repeat OAuth authorization to grant `gitcode:write`; refreshing a tool list or an existing token does not expand it. Existing write grants cover the file publishing tools without a new authorization solely for those tools. Enabling tools does not authorize unrelated writes.

### Publish files with the authorized account

`gitcode_create_file`, `gitcode_update_file` and `gitcode_delete_file` use the current connection's upstream GitCode authorization, with the same read-only, scope and repository restrictions as other writes. They do not require a separate Git credential in dot's execution environment. Each call publishes one file change and one commit; there is no atomic multi-file commit API in this tool surface. Follow [code publishing](code-publishing.md) to prepare, verify and submit the result as a PR.

### Validation boundary

The repository's automated OAuth tests use mocked GitCode endpoints to exercise the HTTP authorization and MCP flows and their failure cases. They do not prove a real GitCode OAuth application, issued credentials, a live domain/certificate or a particular ChatGPT account works. Complete that account-level check before describing a deployment as connected.

OAuth tokens are used for GitCode API calls, including file publishing. The service does not return them for `git clone` or configure credentials on another machine. Native clone, fetch, pull and push use the actual coding environment and its own Git credentials; test execution also requires an execution environment. An API write is not evidence that project tests ran.
