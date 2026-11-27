# Local GitCode accounts

`gc auth login` retains its single-token, offline behavior. To opt into named accounts on **gitcode.com**, run:

```console
gc auth login --account
gc auth login --account
gc auth status
gc auth switch --user alice
gc auth status --active --json hosts
gc auth logout --user bob
```

To name the host explicitly, use `gc auth login --hostname gitcode.com` (or `-h gitcode.com`). Only this bare hostname is accepted, case-insensitively; it does not change the API endpoint, storage, or PAT login method. For login help, use `gc auth login --help`.

At each hidden prompt, enter that account's own personal access token. In automation, pass the token on standard input with `--with-token`; do not put it in a command line, log, or example file. Named login verifies **the supplied token**, not the current environment, using `GET /user`. Only the returned login is used as the account name; an unverified response saves nothing. Signing in again with the same exact login replaces its local token. This is not browser OAuth, SSH setup or a Git credential helper.

- **Selection:** An explicit global `--token` takes priority over `GC_TOKEN`, then the selected local token. An override is never persisted by default. Local login still saves the credential supplied at its prompt/stdin; an override continues to take precedence. When overriding, status shows just the effective credential. Unset the override before using switch, logout or `auth token --user`.
- **Status:** Text shows local selection, not remote token validity; it prints no token or token prefix. JSON verifies each listed token, reports errors per account without the raw upstream response, and exits 0 for verification failures. `--active` selects only the effective account. Only the explicit `auth token` command prints a credential, and `auth token --user LOGIN` requires an exact saved name; avoid these commands in logs.
- **Logout:** Removes a saved token, not the remote PAT. Removing the selected account never promotes another account, even if only one remains. Explicitly select it with `auth switch --user LOGIN`. Switching and logging out are local operations and never contact GitCode.
- **Existing configs:** The old single-token config remains readable without migration. The first named login preserves the old credential under the reserved local slot `@legacy`. Use `auth switch --legacy` to select it or `auth logout --user @legacy` to remove it. An ordinary login replaces only this unnamed slot and selects it. Do not run older clients' login/logout against a multi-account config.
- **Storage:** Credentials remain local plaintext, not keyring entries. Updates atomically replace the existing private file (POSIX directory 0700 / file 0600; user profile ACL on Windows). Concurrent edits are rejected. After a killed writer, remove the empty `~/.config/gc/.auth-update.lock` directory only after confirming that no authentication edit is running.

**OAuth boundary:** GitCode's [documented authorization-code exchange](https://docs.gitcode.com/docs/apis/oauth/) uses a registered client secret. The [confidential MCP server](../gitcode/oauth.md) has a separate flow. The CLI does not ship a client secret or assume GitCode supports public-client PKCE or device codes; `gc auth login --web` is not implemented.
