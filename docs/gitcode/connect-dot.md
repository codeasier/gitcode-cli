# Connect ChatGPT and dot to GitCode

Use a public HTTPS endpoint with GitCode OAuth when the MCP server runs on your cloud server. ChatGPT connects directly to the Server URL; this route has no tunnel client or OpenAI Platform runtime key.

The [Codex marketplace package in `codex-codeasier`](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode) is a separate local stdio installation. Installing that package does not deploy this HTTPS service or register a cloud connection.

## 1. Prepare the public OAuth service

Follow [GitCode OAuth configuration](oauth.md) and [deployment](deployment.md#public-https-with-gitcode-oauth). You need:

- A public HTTPS origin and a valid certificate.
- A GitCode OAuth application whose callback is `https://YOUR_DOMAIN/oauth/gitcode/callback`.
- Independent MCP client credentials to enter in ChatGPT.
- The exact ChatGPT callback in the server's redirect allowlist before account linking.
- Persistent SQLite state and the same encryption key after every restart.

Start with `GITCODE_MCP_READ_ONLY=true`. Use `GITCODE_MCP_OAUTH_ALLOWED_USER_IDS` to restrict a personal service to the intended GitCode IDs and `GITCODE_MCP_ALLOWED_REPOS` to constrain repository access.

OAuth mode uses the credentials acquired by each individual connection. Leave `GITCODE_TOKEN`, `GC_TOKEN` and `GITCODE_MCP_HTTP_TOKEN` out of that service's configuration. For initial setup, the downstream callback allowlist can be empty: discovery remains available, while all authorization callbacks are rejected.

## 2. Add the server in ChatGPT

Use ChatGPT on the web. Workspace permissions and security restrictions still apply.

1. Open **Plugins → + → Add custom MCP server**.
2. Give it a name such as `GitCode`.
3. Under **Connection**, select **Server URL** and enter `https://YOUR_DOMAIN/mcp`.
4. Choose **OAuth**, with explicit client credentials:
   - Client ID: the value of `GITCODE_MCP_OAUTH_CLIENT_ID`.
   - Client secret: the independent `GITCODE_MCP_OAUTH_CLIENT_SECRET`.
   - Client token authentication, where shown: `client_secret_post`.
5. Copy the exact callback displayed for this connection into `GITCODE_MCP_OAUTH_REDIRECT_URIS`. Update the server and restart it before completing account linking; the discovery-only bootstrap cannot authorize a user while that allowlist is empty.
6. Review the displayed connection notice and create the plugin.
7. Open the resulting plugin in **Personal** or the workspace where you created it, and install it.

The server publishes the authorization and token endpoints through metadata. It uses preregistration; do not choose DCR or CIMD for this implementation. The GitCode application ID/secret are upstream server credentials and do not belong in ChatGPT's MCP client fields.

If ChatGPT prompts you to connect an account, complete GitCode's authorization screen, then review the MCP service's client and scope consent screen. For a private deployment, use the GitCode account allowed by the server's stable-ID allowlist.

Official instructions: [Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server), [MCP authentication](https://developers.openai.com/plugins/build/auth), and [connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt).

## 3. Verify a real tool call

In a new conversation, select the installed plugin with `@` and ask:

> Use the GitCode plugin to get repository metadata and clone information for OWNER/REPO. Only read data.

Inspect the actual tool calls and results. Confirm the intended repository and branch, and that clone URLs contain no credentials. A running container, successful HTTPS GET, local stdio smoke test or mocked OAuth test does not establish this ChatGPT connection.

Keep initial acceptance read-only. To publish files or manage Issues/PRs, enable server write mode and refresh the plugin's tools. If the existing grant is read-only, reconnect or repeat OAuth authorization to obtain `gitcode:write`; refreshing tools or an existing token does not elevate it. An existing write grant also covers the file publishing tools and does not need a new authorization solely because these tools were added. GitCode account permissions, branch protections and ChatGPT's action approvals continue to apply.

After changing runtime settings or tool definitions, restart the service, refresh its metadata in ChatGPT and repeat the affected check. Reconnect when the authorization grant expires. See [OAuth operation and lifetimes](oauth.md#4-configure-persistent-state-and-access).

## 4. Publish code and create a PR

Use the [code publishing workflow](code-publishing.md) to create a scoped remote branch, read repository instructions and current files, prepare the change, run available checks, publish files and create a PR. `gitcode_create_file`, `gitcode_update_file` and `gitcode_delete_file` use the existing OAuth connection; no additional Git credentials are needed for these API calls.

Each file write produces a separate commit. Multiple files are published sequentially, not as an atomic batch. Verify returned commit/file identifiers and remote state before opening the PR; stop on an uncertain result instead of automatically retrying.

For native clone, local Git history, commit or push, call `gitcode_get_clone_info` and work in the actual coding environment with its own Git credential helper or SSH identity. The MCP server does not run project tests or execute shell commands.

The MCP service does not expose its tokens or filesystem. A checkout on the MCP host is not automatically visible to dot's shell. A cloud-only custom MCP connection discovers tools but does not automatically install the local `gitcode-workflow` skill.

OpenAI's [dot task documentation](https://learn.chatgpt.com/docs/dots/tasks-and-memory) explains delegation and environment boundaries.

## 5. Upgrade an existing connection

If moving from `codex-codeasier` to `gitcode-cli`, follow [migration and rollback](migration.md) first: keep the existing Server URL, OAuth clients, environment, actual data volume, database and encryption key. Do not create a replacement ChatGPT connection. For subsequent updates, pin the deployed checkout, rebuild or reinstall the runtime, then recreate/restart the service as described in [deployment](deployment.md#operate-and-upgrade). Refresh the plugin's tools in ChatGPT after the new service is running.

A writable connection should now expose 31 tools, including the three file tools; a read-only connection still exposes 19. Existing `gitcode:write` grants do not need reauthorization merely for this upgrade. Reauthorize if a read-only grant needs write scope, the grant has expired, or the GitCode authorization no longer grants the required upstream permissions.

## Other connection routes

- **Local Codex:** use [the stdio plugin setup](setup.md), with its own GitCode PAT or Git credentials.
- **Private stdio host:** the optional [Secure MCP Tunnel guide](connect-tunnel.md) remains available for deployments that explicitly choose that route.
- **Public directory distribution:** creating a personal/workspace connection is separate from submitting a plugin for public distribution.

A cloud-only OAuth connection is added by its HTTPS Server URL. The [`plugins/gitcode/mcp.json` in `codex-codeasier`](https://github.com/codeasier/codex-codeasier/blob/main/plugins/gitcode/mcp.json) remains a portable local stdio manifest; it does not contain your deployment URL or secrets.
