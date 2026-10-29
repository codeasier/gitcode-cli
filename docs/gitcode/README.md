# GitCode MCP

GitCode MCP exposes 31 tools: 19 reads and 12 writes covering repository data, file publishing, issues and pull requests. Its independently installable Python runtime lives in [`packages/gitcode-mcp`](../../packages/gitcode-mcp) in `codeasier/gitcode-cli`. These guides and the deployment templates are client-neutral; the Codex-specific [`gitcode` plugin and workflow skill](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode) remain in `codeasier/codex-codeasier`.

The server supports stdio and Streamable HTTP. Public HTTPS deployments can use the GitCode OAuth broker so each ChatGPT connection authorizes its own GitCode account. The separately maintained Codex marketplace package uses stdio and starts an already-installed `gitcode-mcp` executable in the client's execution environment. It does not download an unpublished PyPI package, install Python dependencies, deploy a service, or connect an account by itself.

## Choose a setup

| Goal | Start here |
| --- | --- |
| Install the runtime or use it from a local Codex environment | [Install and verify](setup.md) |
| Connect ChatGPT/dot directly to a public HTTPS server | [Connect ChatGPT with GitCode OAuth](connect-dot.md) |
| Configure GitCode login, callbacks and persistent credentials | [OAuth configuration](oauth.md) |
| Run a service on a persistent host or in Docker | [Deployment](deployment.md) |
| Move an existing `codex-codeasier` deployment without replacing its OAuth state | [Migration and rollback](migration.md) |
| Explicitly use a private stdio tunnel | [Optional Secure MCP Tunnel](connect-tunnel.md) |
| Inspect the tool surface and write operations | [Tools](tools.md) |
| Publish code to a remote branch and create a PR | [Code publishing](code-publishing.md) |

## Publish code through MCP

`gitcode_create_file`, `gitcode_update_file` and `gitcode_delete_file` write directly to an explicit remote branch through the GitCode Contents API. Each operation produces its own commit. Use a work branch, read repository instructions and current files, prepare and check the changes, then publish files sequentially and verify the result before creating a PR. Updates and deletions require the current file Blob SHA. Multiple file writes are not one atomic commit, and a failure does not roll back earlier writes.

API publishing uses the MCP connection's authorized GitCode account. An OAuth connection with `gitcode:write` and sufficient GitCode permissions does not need a separate SSH identity or PAT in dot's shell for these operations. See [code publishing](code-publishing.md) for examples, limits and failure handling.

## Native Git and code execution

`gitcode_get_clone_info` returns clone URLs without credentials and repository metadata. It does **not** clone a repository or create a directory in dot's workspace.

For work that needs a native Git checkout, local commits or `git push`, choose a coding environment that has Git and its own GitCode authentication. The workflow is:

1. Read the issue and repository through MCP.
2. Obtain clone metadata with `gitcode_get_clone_info`.
3. Clone in the actual coding environment, edit, and run checks there.
4. Commit and push from that environment.
5. Create the PR through MCP using the verified remote branch.

The package also installs `gitcode-clone` for step 3. It supports existing Git credential helpers or SSH, and can use a token through temporary askpass for HTTPS cloning. It does not save that token for future pushes. See [setup](setup.md#clone-in-the-coding-environment).

A dot's cloud computer, a connected computer, a delegated Codex cloud task, and the MCP host can be different machines. Installing a CLI or setting a token on one does not install or authorize it on the others. OpenAI documents these task boundaries in [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) and [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps).

## Runtime requirements

- Python 3.11 or newer.
- The package's pinned MCP SDK and GitCode client dependencies, installed with the package; this migration retains `pygitcode==0.1.6`.
- Runtime package `codeasier-gitcode-mcp` version `0.3.0`, with the unchanged `gitcode-mcp` and `gitcode-clone` commands. This is distinct from the repository's `gc` CLI version.
- Git for `gitcode-clone` and native Git workflows; API file publishing does not require Git.
- For local stdio/static-bearer mode: an authorized GitCode token on the MCP host.
- For public OAuth mode: a registered GitCode OAuth application, distinct MCP client credentials, a public HTTPS origin and persistent encrypted state.
- Separate Git credentials in any environment that performs authenticated native Git operations.

## Release boundary

This repository supplies the runtime source, tests and deployment instructions; local Codex plugin packaging remains in [codex-codeasier](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode). The source move does not publish a PyPI release or deploy an existing service. A Git commit or marketplace installation does not deploy HTTPS, register a GitCode OAuth application, configure user credentials or prove a live dot connection. Automated OAuth tests use mocked upstream endpoints. Complete the actual public HTTP authorization and a read through your ChatGPT connection before enabling the intended write workflow; a stdio smoke check does not verify that route.
