# Deploy GitCode MCP

For a cloud server, deploy Streamable HTTP behind a public HTTPS reverse proxy and enable the GitCode OAuth broker. ChatGPT connects directly to `https://YOUR_DOMAIN/mcp`. Marketplace installation and server deployment remain separate operations.

Runtime source is maintained in `codeasier/gitcode-cli`; all commands below run from its repository root. For an existing deployment from `codex-codeasier`, start with [migration and rollback](migration.md), especially the explicit reuse of the **actual** Docker volume. A fresh-install Compose command is not a state migration.

The GitCode adapter connects to the fixed `https://api.gitcode.com/api/v5/` origin. OAuth also needs `https://gitcode.com/oauth/authorize` and `/oauth/token`. The server does not follow upstream redirects or use environment proxy settings; provide direct GitCode egress from the host.

## Public HTTPS with GitCode OAuth

### Configure the service

Follow [OAuth setup](oauth.md) to create the upstream GitCode application, the independent downstream MCP client credentials and a persistent encryption key. Store the real environment file outside the repository with mode `0600`.

For a **new installation**, use [`compose.oauth.yaml`](../../deploy/gitcode-mcp/compose.oauth.yaml) as a **standalone** Compose file. Do not combine it with `compose.yaml`: the legacy file supplies PAT/static-bearer variables that OAuth mode rejects. Existing named-volume deployments should add [`compose.oauth.upgrade.yaml`](../../deploy/gitcode-mcp/compose.oauth.upgrade.yaml) as described in [migration](migration.md); it requires the verified existing volume and refuses a missing or empty database.

From the repository root:

```bash
docker compose \
  --env-file /absolute/path/to/private/gitcode-oauth.env \
  -f deploy/gitcode-mcp/compose.oauth.yaml \
  up --build -d
```

The service:

- Runs as UID/GID `10001:10001` with a read-only root filesystem.
- Publishes only `127.0.0.1:8765` on the host.
- Stores encrypted OAuth credentials and persistent grant state in the `oauth-data` volume at `/var/lib/gitcode-mcp`.
- Uses `/var/lib/gitcode-mcp/oauth.sqlite3` as its database.
- Starts in read-only mode unless explicitly configured otherwise.
- Restarts automatically according to the Compose restart policy.

The Docker image creates the data directory with ownership for UID 10001. If replacing the named volume with an existing bind mount, give that directory the same ownership and restrict its permissions. SQLite also needs to create its journal files in that directory.

The encryption key is supplied separately from the data volume. Preserve both across upgrades and restarts. Use a single worker/service instance; this deployment does not support multiple replicas sharing its SQLite database.

For a Python installation instead of Docker, install from this checkout into a Python 3.11+ virtual environment, provide the same OAuth variables through the service manager and start:

```bash
gitcode-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

The service account must be able to write its configured database directory. Configure process supervision and startup recovery in the host's existing service manager.

### Configure HTTPS

[`nginx.oauth.conf.example`](../../deploy/gitcode-mcp/nginx.oauth.conf.example) provides a dedicated virtual host and rate-limit zones. Include the file exactly once from the existing Nginx `http {}` context, such as through an existing `conf.d/*.conf` include. It is not a complete `nginx.conf`: do not paste it inside a `server` or `location` block, and do not add a nested `http {}` wrapper when installing it into `conf.d`. Replace the example domain and certificate paths, configure DNS and a valid TLS certificate, then run `nginx -t` before reloading.

The reverse proxy forwards `/mcp`, the OAuth endpoints and discovery metadata to `http://127.0.0.1:8765` without rewriting paths. Leave the backend port private. The example assumes Nginx runs on the host; a containerized proxy needs an explicit private Docker network because its `127.0.0.1` is not the host.

Match `GITCODE_MCP_PUBLIC_URL`, the proxy's fixed Host and `GITCODE_MCP_ALLOWED_HOSTS` to the same public origin. Configure `GITCODE_MCP_ALLOWED_ORIGINS` explicitly. Host and Origin are separate checks: changing the Host allowlist does not authorize an arbitrary browser Origin. If an inspection client sends an additional Origin, add that exact intended value rather than disabling validation.

The application derives OAuth endpoints from the configured public origin. The proxy overwrites forwarded headers, and only a proxy under your control should be trusted to supply them. Do not add a public reverse proxy that supplies a shared internal bearer token to unauthenticated callers.

The sample applies per-source-IP limits only to `/authorize`, `/oauth/start` and `/token`. The first two share a 10-request/minute zone with a burst of 10; `/token` has a separate 30-request/minute zone with a burst of 20. Excess requests receive HTTP 429 without waiting. These are starting values for a personal deployment: clients behind a shared NAT can share an IP, so size the limits for legitimate use. `/mcp`, discovery, the GitCode callback, consent and revocation do not receive these particular limits. If a trusted load balancer sits before Nginx, configure real-IP handling only for that trusted proxy; do not key limits directly on arbitrary forwarded headers.

The application separately caps pending authorization records at 256 and total persistent records at 10,000. The smaller pending limit prevents abandoned unauthenticated flows from consuming the entire credential store. Excess new work is rejected rather than evicting valid grants; expired records are cleaned up. These bounds complement edge limits, not a guarantee against a distributed denial of service. Monitor rejected requests with sanitized counters, and investigate sustained saturation instead of disabling the bounds.

Keep OAuth routes uncached. `access_log off` does **not** control Nginx error logs: upstream failures, limit messages, inherited debug settings and other modules can include a request line with callback `code`/`state`. The example explicitly sets its dedicated error sink to `crit` and rate-limit messages to `notice`, reducing routine request logging instead of inheriting an `info`/`debug` configuration. This still does not guarantee that every diagnostic is free of query values.

The sample file sink can retain raw critical-error context: restrict its readers, retention and rotated-file permissions. For redaction before any disk storage, replace that file sink with a trusted local syslog collector that removes query strings, authorization/cookie headers and request bodies before writing or exporting them. Redacting an already-written file only when forwarding it does not remove the original. Where safe collection cannot be assured, discard raw error output for these OAuth routes and use sanitized application errors/counters. Review effective `error_log`, `debug_connection`, CDN and WAF settings locally before enabling real accounts. Do not enable raw request debugging with production credentials.

The application does not need a client certificate issued by your private CA for this OAuth flow. See Nginx's [request-limit directives](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html) and [error-log settings](https://nginx.org/en/docs/ngx_core_module.html#error_log) for configuration contexts and inheritance.

### Complete account linking

An empty `GITCODE_MCP_OAUTH_REDIRECT_URIS` is a discovery-only bootstrap: the service starts but refuses authorization callbacks. Use it to begin creating the ChatGPT connection and obtain its actual callback URL. Add that exact HTTPS URL to the allowlist, recreate/restart the service, then complete [ChatGPT linking and installation](connect-dot.md).

Discovery must be public. Protected MCP requests require this service's OAuth access token. A generic browser-cookie login proxy, static API key or GitCode PAT is not a substitute for that authorization flow.

### Operate and upgrade

Use the same environment file, explicit Compose project name (if set) and Compose file(s) for subsequent operations. The commands below are for the standalone fresh-install configuration. If the service was migrated with the upgrade override, **keep both `-f` arguments and the required actual-volume setting** on every operation; use the [`compose_new` helper in the migration guide](migration.md#2-prepare-a-separate-pinned-runtime). Dropping that override can create an empty project-scoped volume.

For the standalone configuration:

```bash
docker compose \
  --env-file /absolute/path/to/private/gitcode-oauth.env \
  -f deploy/gitcode-mcp/compose.oauth.yaml \
  logs --tail=50
```

After selecting and verifying the intended full commit SHA in the deployed checkout, rebuild the image and recreate the container to run the new code. Also recreate after changing a secret file or environment setting; a plain restart does not load changed Compose environment values:

```bash
docker compose \
  --env-file /absolute/path/to/private/gitcode-oauth.env \
  -f deploy/gitcode-mcp/compose.oauth.yaml \
  up --build -d --force-recreate
```

Record the deployed commit before upgrading. Back up the SQLite database consistently together with its grant state, keep a separate protected copy of its encryption key, and retain the previous image/commit for rollback. Stop the service during a simple file-level database backup so SQLite journal state is consistent. Do not use `down -v` when stopping a deployment whose authorizations must survive.

The repository-only migration does not alter the SQLite schema or `codeasier-gitcode-mcp.oauth-store.v1` marker and requires neither a database conversion nor reauthorization solely for the source move. Changing the encryption key under an existing database invalidates its stored credentials. This release does not provide an in-place encryption-key rotation command. Plan account reconnection when replacing lost state or keys.

After the new runtime is running, refresh ChatGPT's tool metadata. A writable connection exposes 31 tools, including `gitcode_create_file`, `gitcode_update_file` and `gitcode_delete_file`; read-only connections expose 19. These tools use the existing OAuth authorization for [API code publishing](code-publishing.md), without additional Git credentials in dot's shell.

Update an existing reverse proxy's request-size limit as well: the current Nginx example sets `client_max_body_size 2m`, matching the MCP server's 2 MiB HTTP request limit. This accommodates JSON escaping for file content up to the separate 256 KiB decoded limit. A proxy still using `1m` can reject a valid file-tool request before it reaches the application. OAuth form bodies retain their 16 KiB application limit. Validate and reload Nginx after changing its configuration.

MCP access tokens last at most 15 minutes; a grant's fixed maximum lifetime is 30 days. Account reconnects and upstream revocation can still be necessary. After enabling write mode, a previously read-only grant needs a new OAuth authorization for `gitcode:write`; refreshing it cannot broaden its scopes. An existing write grant does not need reauthorization solely to use newly added file tools.

## Verify the actual deployment

1. From outside the server, verify DNS, the certificate and OAuth discovery at the final HTTPS origin.
2. Confirm an unauthenticated MCP request receives the OAuth challenge.
3. Complete authorization with an allowed GitCode account, including the MCP service's consent step.
4. Use a real MCP client against the HTTPS URL to initialize, list tools and call `gitcode_get_repository` on an allowed repository.
5. Call `gitcode_get_clone_info` and verify credential-free clone URLs.
6. Confirm invalid/expired tokens, disallowed identities, missing write scope and out-of-allowlist repositories are rejected.
7. Check that a service restart preserves authorizations with the same database and encryption key.
8. Repeat a read through the installed ChatGPT connection.

Keep this acceptance read-only; do not create an issue or PR solely to prove deployment. Test actual mutations only when the user authorizes a specific operation.

`python -m gitcode_mcp.smoke` exercises **stdio**, not the HTTPS/OAuth path. Mocked HTTP tests, a running container or a successful HTTP GET do not establish a live GitCode or ChatGPT connection. Deployment and account-level checks must be performed against the service and account you actually use; a successful read does not establish write permission for every repository.

## Existing PAT and static-bearer mode

The default `GITCODE_MCP_AUTH_MODE=bearer` preserves the existing stdio/PAT workflow and controlled HTTP clients. It uses one configured GitCode account per process.

For HTTP, install the runtime and supply `GITCODE_TOKEN` (or `GC_TOKEN`) plus a separate `GITCODE_MCP_HTTP_TOKEN`:

```bash
gitcode-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

The endpoint is `http://127.0.0.1:8765/mcp`. The HTTP bearer secret must have at least 32 characters and differ from the GitCode token. It is required for non-loopback HTTP binding in this mode.

The original [`compose.yaml`](../../deploy/gitcode-mcp/compose.yaml) remains available:

```bash
docker compose -f deploy/gitcode-mcp/compose.yaml up --build -d
```

Supply its secrets through the process environment or a private environment file. It also publishes only loopback port 8765 and defaults to read-only mode. Do not run both deployment variants on that same host port.

Static-bearer mode does not perform GitCode user authorization and is not this project's public ChatGPT OAuth route. Its single PAT must not be shared as though it represented distinct users.

## Optional private stdio tunnel

For environments that explicitly choose a private outbound tunnel, follow [the separate tunnel guide](connect-tunnel.md). Use the default PAT/stdio mode and its own host credentials. The public OAuth deployment above does not use `tunnel-client`, a tunnel ID or `CONTROL_PLANE_API_KEY`.

## Official references

- [Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server)
- [Plugin authentication](https://developers.openai.com/plugins/build/auth)
- [GitCode OAuth](https://docs.gitcode.com/docs/apis/oauth/)
- [GitCode token API](https://docs.gitcode.com/docs/apis/post-oauth-token-grant-type-authorization-code-code-code-client-id-client-id-client-secret-client-secret/)
- [GitCode personal access tokens](https://docs.gitcode.com/docs/help/home/user_center/security_management/user_pat/)
