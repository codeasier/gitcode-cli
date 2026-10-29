# AGENTS.md — `gitcode_cli` package

Parent scope: repository root ([../../AGENTS.md](../../AGENTS.md)) — install/test/lint/release commands live there and are not repeated here. This guide covers the CLI package behind the `gc` / `gitcode` console scripts, not the separately configured MCP package under `packages/gitcode-mcp/`.

## Module map

| Module | Owns | Notable invariants |
|---|---|---|
| `cli.py` | Click root group `main`; `--repo/-R`, hidden `--token`; `version` and `completion` commands; group registration | Catch-all `GCError` → stderr + exit 1 lives in `_GCMainGroup.invoke`. On win32, stdout/stderr are reconfigured to UTF-8 for TTYs. New groups must be registered here **and** in the `set_gc_help` section lists. |
| `commands/` | Click UX per domain: `auth.py`, `issue.py`, `pr.py` (including `audit`), `repo.py`, `compat.py`, `setup.py` | Commands resolve repo, build `Service(app_ctx.client())`, delegate through adapters where gh-semantics translation is needed, then shape output via `formatters.output_result`. Simple reads may use services directly; audit uses `audit.py`. Unimplemented-but-recognized flags raise `_pending_gh_compat("<key>")`; GitCode-impossible flags raise `unsupported("<CAPABILITY_KEY>")`. Both literals are test-policed (see the compat guide). |
| `adapters/` | gh-semantics → GitCode translation | See [adapters/AGENTS.md](adapters/AGENTS.md). |
| `services/` | Thin REST wrappers: `issues.py`, `pulls.py`, `users.py`, `repos.py` | Issue/PR path shapes are contract-tested against `tests/fixtures/gitcode-api-contracts/raw/`. Issue create uses `POST /repos/{owner}/issues`; update uses `PATCH /repos/{owner}/issues/{number}`. Both put `repo` in the JSON body (not the path) — do not infer these shapes from PR endpoints. `PullRequestService.list_issues`, `list_files` and `list_comments` share guarded internal pagination at `per_page=100` (rejecting malformed/repeated pages and excessive page counts); `diff()` requests `text/plain`. |
| `client.py` | `GitCodeClient`: httpx wrapper, `BASE_URL = "https://api.gitcode.com/api/v5/"` | Merges `access_token` into every request's query params and adds `private-token` only for the repository method/path allowlist (`_requires_private_token`); services own no credential policy. Drops `None` param values; 30s timeout; 401 → `APIError` with a "run gc auth login" hint; other ≥400 → `APIError`; httpx transport errors → `NetworkError`. |
| `audit.py` | `gc pr audit` data collection and rule evaluation | Uses `PullRequestService` for official linked issues, comments, files and diff fallbacks. Keeps unavailable/unknown data distinct from verified results; HTTP 401 aborts remaining list-mode work. |
| `config.py` | Token persistence: `~/.config/gc/config.json` | Tests monkeypatch `CONFIG_DIR`/`CONFIG_PATH` module attributes (see `tests/conftest.py` `tmp_config_dir`). |
| `context.py` | `AppContext` dataclass (`token`, `repo`) with `client()` factory | Command tests replace `AppContext.client` via the `mock_app_context` fixture — keep the factory a single method. |
| `repo.py` | Repo string / remote URL parsing | `parse_repo_with_host` accepts `OWNER/REPO` and `HOST/OWNER/REPO`; host detection here feeds gh-proxy routing. |
| `errors.py` | `GCError` → `ConfigError`, `AuthError`, `RepoResolutionError`, `APIError(status_code)`, `NetworkError` | Only `GCError` subtypes get the graceful one-place exit handling in `cli.py`. |
| `formatters.py` | Output shaping: `--json` field filtering, `-q` jq, `-t` Go-template subset, list/detail renderers | `apply_jq` needs either the Python `jq` module or a `jq` binary on PATH — neither is a package dependency, so `--jq` can fail at runtime by design. Templates support only `{{.a.b}}`, `{{range .}}`, and `{{"\n"}}`. |
| `helptext.py` | gh-style grouped help rendering (`GCSectionGroup`, `set_gc_help` metadata) | Help text comes from attributes like `gc_command_sections`/`gc_examples` set via `set_gc_help`, not from docstrings alone. |
| `utils.py` | git subprocess helpers, issue/PR URL+number identifier parsing, `safe_echo` (encoding-safe) | `resolve_pr_arg` accepts number, URL, or branch (branch triggers an API lookup). |
| `cli_compat.py` | Shared command helpers: `--body`/`--body-file`/`--editor` resolution and `--fill[-first\|-verbose]` git-log extraction | Despite the name, this is not the gh-compat registry — that is `compat/`. |
| `gh_proxy.py` + `commands/setup.py` | Optional `gh` dispatcher subsystem | See below. |
| `compat/` | gh-compatibility registry | See [compat/AGENTS.md](compat/AGENTS.md). |

## Layering rules (what must change together)

Adding or changing a user-facing flag typically touches four places in one PR:

1. The Click option in `commands/` (parsing, validation, help).
2. The translation in `adapters/` (new capability keys go in `adapters/capabilities.py` `CAPABILITY_MESSAGES`).
3. The registry row in `compat/entries.py` with the matching `pending_key` / `unsupported_key`.
4. Tests in `tests/unit/commands/` and/or `tests/unit/adapters/`.

`tests/unit/compat/test_registry_consistency.py` checks registry keys and literal guards. `tests/unit/commands/test_cli_gh_compat.py` separately checks selected Click commands/flags against the baseline fixture. These checks do not prove all behavior or every possible registry-to-Click invariant; add focused tests for the behavior being changed.

Output changes (`--json` field lists, `-t` templates, human formats) should extend the `gc_json_fields` metadata consumed by `helptext.py` and the normalization helpers in `commands/issue.py` / `commands/pr.py` / `commands/repo.py` (e.g. `_normalize_pr_fields` back-fills `mergedAt` from `merged_at`, `_normalize_closing_issue` maps `OPENED` → `OPEN` state).

Changes to `client.py` or service call signatures also affect non-CLI consumers. MCP currently installs a pinned published CLI version and overrides `GitCodeClient.request`; preserve compatibility and validate explicitly rather than assuming root unit tests exercise the sibling MCP source. The `gitcode-mcp-services.yml` gate verifies an installed checkout against the full MCP suite without changing its production dependency pin.

`commands/repo.py` validates repository hosts and path segments for positional, command/global `-R`, and origin-derived targets before calling services; do not replace that with `resolve_repo()`, which drops the host. Rename updates only a matching GitCode origin and never prints its URL/userinfo.

## gh dispatcher subsystem (`gh_proxy.py`, `commands/setup.py`)

`gc setup gh-proxy` installs a `gh` shim next to nothing else — it never touches a real `gh` installation:

- Shim location: `~/.local/share/gc/gh-proxy/gh` (`%LOCALAPPDATA%\gc\gh-proxy\gh.cmd` on Windows), overridable with `GC_GH_PROXY_DIR`. The shim sets `GC_GH_SHIM` and execs `python -m gitcode_cli.gh_proxy`.
- File-level marker protection applies to the shim (`Generated by gc setup gh-proxy`) and `gh-proxy-instructions.md` (`<!-- Generated by gc setup gh-proxy -->`): unmanaged versions are not overwritten or removed.
- Shell profiles are different: configuration appends or replaces the managed PATH block (`# >>> gc gh-proxy >>>` / matching end marker), and uninstall removes that block while retaining surrounding content. The profile file itself is rewritten, including when no block existed before configuration.
- OpenCode's JSON config does not require a managed-file marker. Configuration updates its `instructions` array and serializes the file while preserving other fields; uninstall removes the managed instruction reference. Do not confuse these scoped configuration edits with protection against writing the whole file.
- Routing (`gh_proxy.select_target`): `GC_GH_TARGET=gitcode|github` > host in explicit `-R`/`--repo` > repository positional host for `repo view/clone/fork/edit/delete/sync` (skipping option values) > `origin` host > default `github`. `gitcode.com` and `ssh.gitcode.com` are GitCode by default; `GC_GITCODE_HOSTS` adds more. `GC_REAL_GH` locates the native CLI when PATH discovery fails.
- GitCode-bound commands are fail-closed: `validate_gitcode_command` only accepts subcommands present (and not `not_in_cli`) in the compat registry — a command missing from the registry is an error, never a silent GitHub fallback.
- Dispatch to `gc` uses `os.execve` on POSIX (argument/stream/exit-status preserving) and `subprocess.call` on Windows, and exports `GC_GH_PROXY_ACTIVE=1` (consumed by `auth status` to print a proxy notice).
- `--configure` additionally writes a managed PATH block into the detected shell profile (`GC_GH_SHELL_PROFILE` override; zsh → `~/.zshenv`, bash → `~/.bash_profile` on macOS / `~/.bashrc` elsewhere, fish, PowerShell) and appends `gh-proxy-instructions.md` to the `instructions` array of `~/.config/opencode/opencode.json` (`GC_OPENCODE_CONFIG` override).

## Platform-dependent behavior

- Windows: use `gitcode` rather than `gc` (PowerShell alias collision); stdout/stderr are reconfigured to UTF-8 for TTYs when supported (`cli.py`); the shim is a `.cmd` batch file; proxy exec goes through `subprocess.call` instead of `execve`.
- `commands/setup.py` picks the shell profile file by `$SHELL` and `sys.platform` — changes here need coverage for more than one platform path.
