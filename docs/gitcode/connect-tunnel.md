# Optional private stdio tunnel

Use this guide only when you explicitly choose a private stdio tunnel. For a cloud server with a public HTTPS address, use [direct OAuth connection](connect-dot.md). The [Codex marketplace package in `codex-codeasier`](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode) launches a local stdio process and is marked as requiring a local executor. Installing it in a local Codex client does not register cloud tools for dot.

This alternative connects **Secure MCP Tunnel to the server's stdio entry point**. It requires OpenAI tunnel permissions and a GitCode PAT configured on the host. Use the default `GITCODE_MCP_AUTH_MODE=bearer` for this stdio process; the public OAuth broker uses Streamable HTTP instead.

## 1. Prepare a persistent MCP host

Follow [Install and verify](setup.md) on a host that can reach GitCode and make outbound HTTPS requests to OpenAI. Record the absolute path to its installed `gitcode-mcp` executable. Configure the GitCode token, repository allowlist, and initial read-only mode in the environment that will start `tunnel-client` and its child server.

Keep this host available for tool discovery and every later tool call. The MCP host need not be dot's code-editing environment.

## 2. Create or select an OpenAI tunnel

Open [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels). Use the actual tunnel ID returned there, and associate the tunnel with the target ChatGPT workspace as well as its Platform organization.

Creating or editing a tunnel requires **Tunnels Read + Manage**. Running the client or selecting the tunnel in ChatGPT requires **Tunnels Read + Use**. These permissions are separate from the ChatGPT account's ability to add custom MCP plugins.

Download the supported `tunnel-client` from that page or the official [OpenAI release](https://github.com/openai/tunnel-client/releases/latest). Supply its restricted runtime key as `CONTROL_PLANE_API_KEY` through a secret manager or a hidden interactive prompt:

```bash
read -r -s -p 'OpenAI tunnel runtime key: ' CONTROL_PLANE_API_KEY
export CONTROL_PLANE_API_KEY
```

The runtime key authenticates to the OpenAI tunnel service. The GitCode token authenticates this MCP server to GitCode. Neither belongs in tool arguments or tool results.

## 3. Start the stdio tunnel

Replace the tunnel ID and executable path below with your actual values:

```bash
tunnel-client help quickstart
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile gitcode \
  --tunnel-id 'tunnel_REPLACE_WITH_ACTUAL_ID' \
  --mcp-command '/absolute/path/to/gitcode-mcp'
tunnel-client doctor --profile gitcode --explain
tunnel-client run --profile gitcode
```

The client initiates outbound HTTPS to `api.openai.com:443`; no inbound public MCP listener is needed. Keep `run` active. For a persistent service, use your service manager to supply the same profile and environment, and stop the old stdio client before starting its replacement. Use the client's health/readiness checks and logs to verify polling.

See the current [Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) for permissions, workspace association, proxies, custom certificates, and connection diagnostics.

## 4. Register the custom MCP plugin

In ChatGPT on the web:

1. Open **Plugins**, select **+**, then **Add custom MCP server**.
2. Enter a name such as `GitCode private`.
3. Under **Connection**, choose **Tunnel** and select the tunnel or enter its actual ID.
4. For this private stdio setup, choose **No authentication** at the MCP application layer. Access to the tunnel is controlled by OpenAI; the GitCode upstream credential stays on the host. This configuration represents that host's configured GitCode account.
5. Review the displayed connection warning, create the plugin, inspect the tools, and install it.

These steps register a connection; pushing this repository to GitHub does not perform them. If Tunnel is absent or the tunnel is not listed, check workspace association and permissions in the official guide. Do not substitute a secret-bearing public URL.

## 5. Verify through dot

Ask dot to use the installed GitCode plugin to read an allowed repository and obtain its clone metadata. Check the tool call and result, not just the natural-language response. Confirm the repository, branch, and credential-free clone URL match what you intended.

Enable the required write operations only after the actual account and tool connection have been checked. Account/workspace restrictions can differ from the general developer documentation. Validate a narrowly scoped write on a repository you control before relying on Issue/PR automation; this project does not assert that every account has identical custom-MCP write access.

After changing tool definitions or runtime configuration, restart the server, refresh the connection's tools in ChatGPT, and repeat the affected checks. See [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt).

## 6. Publish code or use a Git execution environment

For API code publishing, follow the [file publishing workflow](code-publishing.md). Create a scoped branch, read instructions and current files, prepare and check the change, then use the file tools sequentially and verify the result before creating a PR. These tools use the MCP server's configured GitCode account; no separate Git credentials are required for the API writes.

For native clone, commit and push, call `gitcode_get_clone_info` and use a connected computer or prepared coding environment. Install the runtime there if using `gitcode-clone`, and configure that environment's Git authentication separately. Project tests also run in an actual execution environment, not through the MCP server.

The MCP server does not return its token or mount its filesystem in dot. A directory created by a remote server would not become visible to dot's shell. The workflow skill is available in the [local Codex plugin package](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode); a cloud-only custom MCP connection discovers the server tools but does not automatically import that local skill file.

OpenAI's [dot task documentation](https://learn.chatgpt.com/docs/dots/tasks-and-memory) describes delegation and environment boundaries. Current [Codex Cloud setup](https://learn.chatgpt.com/docs/environments/cloud-environments) documents GitHub repository selection; this project does not claim native GitCode environment provisioning.

## Other distribution routes

- **Local Codex:** install the runtime from `gitcode-cli` and the `gitcode` plugin from `codex-codeasier` using [setup](setup.md).
- **Workspace GitHub import:** OpenAI currently marks imported packages declaring `mcp.json`/`.mcp.json` as Desktop only, including remote HTTP entries. A supported cloud workflow can instead reference an already-registered app, with its existing access and authentication. See [Plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management).
- **Public directory submission:** deploy a stable authenticated HTTPS endpoint and follow the separate public submission process. Secure MCP Tunnel alone does not satisfy public submission requirements.

The separate static HTTP bearer mode remains intended for controlled clients. For ChatGPT's public Server URL route, use the implemented [GitCode OAuth mode](oauth.md), which maintains a distinct GitCode authorization per connection.
