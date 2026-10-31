# Codeasier GitCode MCP

An independently installable MCP server for GitCode repositories, file publishing,
issues and pull requests. It reuses `pygitcode` services and supports stdio and Streamable HTTP.
Public HTTPS deployments include a GitCode OAuth broker for connecting ChatGPT
directly by Server URL.

Requires Python 3.11 or later. From a checkout of `codeasier/gitcode-cli`:

```sh
python -m pip install ./packages/gitcode-mcp
gitcode-mcp --help
python -m gitcode_mcp.smoke
```

For local stdio or controlled static-bearer HTTP clients, supply `GITCODE_TOKEN`
(or `GC_TOKEN`) through the process environment or your secret manager. This is the
default `GITCODE_MCP_AUTH_MODE=bearer`. Set `GITCODE_MCP_READ_ONLY=true` to expose only read tools and
`GITCODE_MCP_ALLOWED_REPOS=owner/repository,owner/other` to constrain repository
access. Tokens are never MCP tool arguments.

For public HTTP, set `GITCODE_MCP_AUTH_MODE=oauth` and follow the
[OAuth setup guide](https://github.com/codeasier/gitcode-cli/blob/main/docs/gitcode/oauth.md).
Configure a GitCode OAuth application, a separate preregistered MCP client, exact
HTTPS callbacks, and persistent encrypted SQLite state. OAuth mode rejects PAT
and static HTTP bearer configuration; each authorized connection uses its own
GitCode identity and receives separate MCP access tokens. It supports PKCE,
explicit consent, refresh and revocation, with a fixed authorization lifetime.
The environment-file and Compose examples are in `deploy/gitcode-mcp`.

The server exposes 31 tools: 19 reads and 12 writes. `gitcode_create_file`,
`gitcode_update_file` and `gitcode_delete_file` publish a single file change to an
explicit remote branch using GitCode's Contents API. Updates and deletions require
the current file Blob SHA. Each call creates a separate commit; there is no atomic
multi-file commit or force-ref operation. See the
[code publishing guide](https://github.com/codeasier/gitcode-cli/blob/main/docs/gitcode/code-publishing.md)
for limits, verification and the Issue-to-PR workflow.

These API writes use the connection's GitCode authorization. OAuth connections
with `gitcode:write` and the required upstream permissions need no additional Git
credentials for file publishing. The server's read-only mode and repository
allowlist still apply. After upgrading the runtime, restart it and refresh the
client's tool metadata. Existing write grants cover these tools; an existing
read-only grant needs a new authorization to obtain write scope.

The built-in smoke command checks stdio. Automated OAuth tests use mocked GitCode
responses; verify the final HTTPS authorization flow and a real ChatGPT read before
considering a deployment connected.

The separate `gitcode-clone OWNER/REPO DESTINATION` command clones into the machine
where it is executed. A remote MCP connection does not share its filesystem with
dot or Codex. Run this helper in the actual coding environment, using an existing
Git credential helper, SSH, or the documented temporary PAT authentication.
The MCP server does not execute a shell or run project tests. Native Git operations
and test execution remain tasks for an actual coding environment.

See the repository's [setup and operation guide](https://github.com/codeasier/gitcode-cli/tree/main/docs/gitcode)
for local plugin installation, direct HTTPS/OAuth connection, the optional private
tunnel route and the Issue-to-PR workflow. This source package is not assumed to
be published on PyPI.

## Migration provenance and compatibility

This package was imported from `codeasier/codex-codeasier` at
`f93b67bb7048e556b44322d48664522f32651920` (PR #8, subsequently merged as
`27b542521c8483b5cf051ae001e791e08e92bb40` with the same tree).
[`MIGRATION_SOURCE.json`](MIGRATION_SOURCE.json) records the original file mapping
and blob hashes; [`LICENSE`](LICENSE) retains the original MIT copyright notice.
The original regression tests preserve that baseline. The CLI package remains
separately versioned: this source now pins the published `pygitcode==0.1.7`, rather
than implicitly importing a sibling checkout. The MCP version remains `0.3.0`;
this dependency change does not publish or deploy an MCP release.

The existing file-read/create/update/delete tools delegate to the installed
`FileService`. MCP still owns its stricter path policy (including rejection of
literal `?`, `#` and `%`), canonical Base64 and size limits, explicit branch and
expected Blob SHA requirements, authorization, and normalized results. The
service receives decoded paths and quotes them exactly once, then uses MCP's
bounded bearer-only transport. No tool, schema, retry, automatic SHA refresh or
multi-file atomicity is added.

The existing `gitcode_get_repository` and `gitcode_get_clone_info` tools also
delegate their single metadata read to the installed `RepoService.get`. MCP
retains repository validation and allowlists, bearer-only transport, response
redaction, and credential-free clone URLs. This does not add tools or consume
unreleased CLI service methods.

Normal tests exercise this published dependency. A separate artifact matrix
installs the actual CLI wheel and sdist on Python 3.11–3.13, verifies their hashes
and installed origin, and runs both `tests/` and `tests_source/` in isolation.
Separately,
`gitcode-mcp-services.yml` installs the CLI checkout with `--no-deps`, verifies all
installed client/service hashes, and explicitly runs `tests_source/` and
`tests_checkout/` alongside the full MCP suite. The latter directory tests
unreleased repository branch/tree/commit primitives directly with MCP's
transport, not production tool delegation. It is excluded from normal pinned
tests and the published `0.1.7` artifact matrix. Production consumption requires
a separately authorized CLI release, real artifact validation and a subsequent
consumer change. That forward-compatibility probe does not change the exact
production pin or authorize consuming unreleased services. Migration acceptance
keeps the immutable legacy MCP `0.3.0` / `pygitcode==0.1.6` installation for seed
and rollback; candidate checks require `pygitcode==0.1.7` even though its MCP
version is also `0.3.0`.

See the [migration and rollback guide](../../docs/gitcode/migration.md) before
upgrading an existing OAuth deployment. Repository migration does not authorize
a production switch, change the state schema or encryption key, or require new
user grants. A destination CI pass is required before switching a downstream
bridge to its exact commit or artifact.

## Independent release preparation

See the [release guide](../../docs/gitcode/releases.md) for `mcp-vX.Y.Z` tags,
artifact gates, and the separately authorized PyPI setup. Manual release-workflow
runs validate only; they cannot publish. Merging this workflow does not publish a
package, change downstream pins, or deploy a server.
