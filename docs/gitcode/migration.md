# Migrate an existing GitCode MCP deployment

The MCP runtime moves from `codeasier/codex-codeasier` to **`codeasier/gitcode-cli`**. The first import is based on [source commit `f93b67bb7048e556b44322d48664522f32651920`](https://github.com/codeasier/codex-codeasier/commit/f93b67bb7048e556b44322d48664522f32651920). The import's provenance is recorded in [`MIGRATION_SOURCE.json`](../../packages/gitcode-mcp/MIGRATION_SOURCE.json), with the source copyright preserved in the package [`LICENSE`](../../packages/gitcode-mcp/LICENSE). Runtime source, general documentation and deployment templates retain their paths: `packages/gitcode-mcp`, `docs/gitcode` and `deploy/gitcode-mcp`.

This is a source-repository migration, not a new OAuth deployment or a package release. The runtime remains **`codeasier-gitcode-mcp` `0.3.0`**, with the **`gitcode-mcp` / `gitcode-clone`** commands and **`pygitcode==0.1.6`**. Do not infer the MCP version from the repository's separate `gc` CLI version or install an assumed future PyPI release. The Codex-specific [plugin, stdio manifest and workflow skill](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode) stay in `codex-codeasier`; local plugin setup remains documented in [setup](setup.md#install-the-codex-plugin).

## Compatibility contract

For an existing deployment using the imported runtime, change only the source checkout/image or installed package. Preserve:

- The public origin, `/mcp` Server URL, discovery/OAuth URLs, reverse-proxy routes and existing ChatGPT connection.
- Both OAuth clients: the upstream GitCode application and downstream MCP client, their existing IDs/secrets, and exact callback allowlists. Do not recreate either client or regenerate credentials.
- The existing private environment file/secret-manager configuration, environment-variable names, read/write mode, account/repository restrictions, Host/Origin allowlists and service settings. Do not replace these with fresh-install defaults.
- The **actual existing** SQLite database and all persisted grant/token state; the in-container default remains `/var/lib/gitcode-mcp/oauth.sqlite3`.
- The original `GITCODE_MCP_OAUTH_ENCRYPTION_KEY` (Fernet key), permissions and storage ownership. Keep the key outside the database backup and source control.
- The existing SQLite schema and encrypted marker **`codeasier-gitcode-mcp.oauth-store.v1`**. There is no schema conversion, data export/import or marker rewrite in this migration.

With the same state, credentials and URLs, moving repositories does **not itself require reauthorization**. Existing expiry, revocation and scope rules still apply: expired grants, revoked upstream access or a deliberate read-to-write scope change may require a new authorization. Do not promise that previously expired credentials will become valid again.

Use **one service instance/worker**. Stop the old process before starting the new one; never run both against the same SQLite store. Keep the old runtime and its configuration available for rollback. These instructions do not authorize a production deployment, proxy/security change or write to a GitCode repository; perform those only within the operator's existing authorization.

## Offline validation is not production acceptance

Static checks and repository CI can check package installation/building, protocol behavior, offline storage compatibility and deployment-template wiring. Inspect the checks on the exact target commit; a proposed or unrun check is not a pass. These checks use source/configuration or isolated fixtures, not the production OAuth database, real GitCode authorization or a live ChatGPT connection.

This document is an operator runbook, not evidence that a production migration has happened. The stop/backup/start actions and real HTTPS/refresh/read/rollback checks below remain deployment-time acceptance steps. No existing service, production database or OAuth registration is changed by adding these files.

## 1. Inventory the running deployment without exposing secrets

Record the current source revision, exact running image ID (or virtual environment/executable), supervisor, public URL, private configuration location and storage mount. Retain the old checkout and container. Do not print or paste environment values, tokens, authorization headers, database rows, full `docker inspect` output or resolved `docker compose config` output.

For the supplied Docker layout, set `OLD_CONTAINER` to the verified old container name/ID and inspect **only mount metadata**:

```bash
: "${OLD_CONTAINER:?Set the existing GitCode MCP container name or ID}"
docker container inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/var/lib/gitcode-mcp"}}{{.Type}} {{.Name}} {{.Source}} -> {{.Destination}}{{println}}{{end}}{{end}}' \
  "$OLD_CONTAINER"
docker container inspect --format '{{.Image}}' "$OLD_CONTAINER"
docker container inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$OLD_CONTAINER"
```

If the mount type is `volume`, record its **Name**, not the logical Compose key `oauth-data`. Compose often prefixes a volume with a project name; a changed checkout/project can otherwise select or create a different empty volume. Use the observed name even if it does not follow that convention. Verify the mount contains the established `oauth.sqlite3`, not an empty or unrelated directory. Do not create a volume to make the upgrade pass.

Set `GITCODE_MCP_OAUTH_VOLUME_NAME` to that verified existing name through the operator's shell/configuration, then check that it exists:

```bash
: "${GITCODE_MCP_OAUTH_VOLUME_NAME:?Set the actual existing volume name from the old container}"
docker volume inspect --format '{{.Name}}' "$GITCODE_MCP_OAUTH_VOLUME_NAME"
```

The upgrade override below is for the supplied **named-volume layout and default database path**. If the old deployment instead uses a bind mount, a different database path, custom command or service manager, preserve that exact layout/settings in its reviewed configuration; do not switch it to this default volume template. Existing directories must remain writable by the service's UID/GID `10001:10001`, with private permissions. Never delete state to fix a startup or encryption-key error.

## 2. Prepare a separate pinned runtime

Choose a reviewed **full, lowercase 40-character commit SHA in `codeasier/gitcode-cli` that contains the migrated package**. Supply it as `GITCODE_MCP_REVISION`; no target SHA is guessed here before the migration is committed. A mutable `main`/branch name or the old repository's source SHA is not a target pin. Record the selected SHA with the old revision/image for rollback.

In Bash, set `GITCODE_MCP_CHECKOUT` to a new absolute checkout path and run:

```bash
set -euo pipefail
: "${GITCODE_MCP_REVISION:?Set the reviewed full gitcode-cli commit SHA}"
: "${GITCODE_MCP_CHECKOUT:?Set a new absolute path for the gitcode-cli checkout}"
[[ "$GITCODE_MCP_REVISION" =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' 'A full lowercase commit SHA is required.' >&2; exit 1; }
[[ "$GITCODE_MCP_CHECKOUT" = /* ]] || { printf '%s\n' 'An absolute checkout path is required.' >&2; exit 1; }
git clone --no-checkout https://github.com/codeasier/gitcode-cli.git "$GITCODE_MCP_CHECKOUT"
git -C "$GITCODE_MCP_CHECKOUT" fetch origin "$GITCODE_MCP_REVISION"
git -C "$GITCODE_MCP_CHECKOUT" checkout --detach "$GITCODE_MCP_REVISION"
test "$(git -C "$GITCODE_MCP_CHECKOUT" rev-parse HEAD)" = "$GITCODE_MCP_REVISION"
test -f "$GITCODE_MCP_CHECKOUT/packages/gitcode-mcp/pyproject.toml"
```

For Docker, set `GITCODE_MCP_ENV_FILE` to the **existing** absolute private environment-file path, and `GITCODE_MCP_COMPOSE_PROJECT` to a new, unused Compose project name, distinct from the old container's project. Keeping the projects separate preserves the stopped old container and image for rollback. Check that no unrelated deployment already uses the chosen new name. Resolve any stale exported variables that would override the private file; do not change the effective service credentials or restrictions.

Use this Bash helper for **every** operation on the new deployment, including later upgrades. Both `-f` arguments are required. Relative build paths resolve from the first file, so `context: ../..` still points to the new repository root and the Dockerfile still copies `packages/gitcode-mcp`.

```bash
: "${GITCODE_MCP_ENV_FILE:?Set the existing absolute private environment-file path}"
: "${GITCODE_MCP_COMPOSE_PROJECT:?Set a new unused Compose project name}"
: "${GITCODE_MCP_OAUTH_VOLUME_NAME:?Set the verified existing volume name}"
[[ "$GITCODE_MCP_ENV_FILE" = /* && -f "$GITCODE_MCP_ENV_FILE" ]] || { printf '%s\n' 'An existing absolute private environment-file path is required.' >&2; exit 1; }
OLD_PROJECT="$(docker container inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$OLD_CONTAINER")"
[[ "$GITCODE_MCP_COMPOSE_PROJECT" != "$OLD_PROJECT" ]] || { printf '%s\n' 'Use a separate project to preserve the old container for rollback.' >&2; exit 1; }
export GITCODE_MCP_OAUTH_VOLUME_NAME
compose_new() {
  docker compose \
    --project-name "$GITCODE_MCP_COMPOSE_PROJECT" \
    --env-file "$GITCODE_MCP_ENV_FILE" \
    -f "$GITCODE_MCP_CHECKOUT/deploy/gitcode-mcp/compose.oauth.yaml" \
    -f "$GITCODE_MCP_CHECKOUT/deploy/gitcode-mcp/compose.oauth.upgrade.yaml" \
    "$@"
}
compose_new build
```

The [upgrade override](../../deploy/gitcode-mcp/compose.oauth.upgrade.yaml) declares `external: true` and requires the actual volume name; a missing name or missing volume fails rather than creating a replacement. It also refuses to start if the database file is missing or empty, even in an existing volume. The runtime validates the schema and encrypted marker with the unchanged key. None of these checks proves that an unrelated nonempty volume is the right one: verify the mount identity first.

For a **new installation only**, the unmodified [standalone OAuth Compose file](../../deploy/gitcode-mcp/compose.oauth.yaml) continues to initialize its own named volume. Do not combine either OAuth file with the PAT/static-bearer `compose.yaml`.

## 3. Stop the old service and back up state

Schedule a brief interruption and let in-flight requests complete. Stop the old instance through its actual supervisor; for the retained Docker container:

```bash
docker stop "$OLD_CONTAINER"
test "$(docker container inspect --format '{{.State.Running}}' "$OLD_CONTAINER")" = false
```

Ensure no second worker, automatic restart job or other supervisor can start the old runtime while the new one is active. Do **not** remove the old container/image or run `docker compose down -v`, `docker volume rm` or volume pruning.

With every writer stopped, make a consistent protected backup of the existing SQLite database and any journal/sidecar files using the deployment's established backup procedure. A cold backup of its complete private data directory avoids copying a database mid-transaction. Retain ownership and restrictive permissions. Separately back up the existing private configuration and Fernet key in protected storage; do not print or paste their contents. Verify the backup is usable before continuing. Do not initialize, vacuum, convert or rewrite the store as part of moving repositories.

## 4. Start exactly one new instance

Only after the old instance is stopped and the backup is verified:

```bash
compose_new up --no-build -d --scale gitcode-mcp=1
compose_new ps
```

Inspect the new container's mount using the same restricted mount-only template from step 1, and confirm it maps the **same actual volume** to `/var/lib/gitcode-mcp`. Confirm the new container uses the image built from the recorded target SHA. Check sanitized startup diagnostics for storage/key errors without dumping environment or OAuth requests. If the volume is absent, the database is missing/empty, the key does not match, or the old service is still active, stop and investigate; do not regenerate keys, create an empty database or reconnect accounts to conceal the mismatch.

Do not change DNS, the reverse proxy, OAuth applications, callback allowlists or the existing ChatGPT Server URL merely because the runtime repository changed.

## 5. Verify the existing connection

1. Check the unchanged public origin, certificate, discovery metadata and unauthenticated MCP OAuth challenge.
2. Through the **existing** ChatGPT/MCP connection, initialize/list tools and read an allowed repository with `gitcode_get_repository`; verify the intended account/repository result. Do not begin by creating a new connection or reauthorizing.
3. Read `gitcode_get_clone_info` and check that its URLs contain no credentials. The read-only catalog still has 19 tools; an existing writable connection has 31.
4. Verify that existing access survives token refresh and a controlled service restart with the same volume and key. Keep the upgrade override for every Compose operation.
5. Confirm the original account/repository restrictions and scope enforcement remain effective, and that only one service instance is running. Keep acceptance read-only; do not create a file, Issue or PR just to test migration.

A successful container start, HTTPS GET, local stdio smoke command or mocked test does not prove this account-level migration. Report unperformed checks as unverified; the repository move itself does not establish production acceptance.

OAuth authorizes GitCode **API** calls, including the MCP file tools. It does not supply native `git push` credentials or expose the server's tokens/filesystem. Native Git operations still need the actual coding environment's credential helper or SSH identity; project tests still run in that environment.

## 6. Roll back without losing the existing store

If the new runtime fails acceptance, stop it before restarting the old instance:

```bash
compose_new stop gitcode-mcp
# Confirm the new instance is stopped before starting the retained old container.
compose_new ps --all
docker start "$OLD_CONTAINER"
```

Use the actual original supervisor for non-Docker installations. Run the retained old image/runtime with its unchanged private configuration and the **same current** data volume/database and Fernet key, then repeat a read through the existing connection. This import changes no storage schema, so ordinary runtime rollback needs no data conversion or backup restore. Never run both instances against the store, and do not remove the shared volume when cleaning up the failed deployment.

Prefer the current store over restoring an older snapshot: OAuth refresh and revocation can update state after the backup, and reverting it can restore stale upstream refresh tokens. If disaster recovery requires a backup restore, stop every writer and restore a consistent matched database/configuration/key set through the protected recovery procedure. Upstream revocation, expired grants or rotated refresh tokens may then require reauthorization; a database restore cannot undo those external changes.

## Non-Docker and local stdio installations

Keep the same public endpoint, service manager, private environment and absolute SQLite path for a virtual-environment service. Install from the reviewed target checkout into a separate Python 3.11+ virtual environment, preserve the old environment, then use the same stop/backup/single-instance/verify/rollback sequence when changing the supervised executable. Do not run the new OAuth service while the old one is using the store.

For local stdio, install the package from the pinned `gitcode-cli` checkout following [setup](setup.md#install-the-runtime-from-this-repository); `uv tool install --reinstall ./packages/gitcode-mcp` replaces the existing local tool installation. Preserve the process's PAT/allowlists and the original Codex plugin registration from `codex-codeasier`. The plugin still resolves `gitcode-mcp` on its execution host's `PATH`; moving the runtime source does not install it on another computer or change native Git authentication.
