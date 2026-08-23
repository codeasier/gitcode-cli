# AGENTS.md — `gitcode_cli` package

Parent scope: repository root ([../../AGENTS.md](../../AGENTS.md)) — install/test/lint/release commands live there and are not repeated here. This guide covers the single installable package behind the `gc` / `gitcode` console scripts.

## Module map

| Module | Owns | Notable invariants |
|---|---|---|
| `cli.py` | Click root group `main`; `--repo/-R`, hidden `--token`; `version` and `completion` commands; group registration | Catch-all `GCError` → stderr + exit 1 lives in `_GCMainGroup.invoke`. On win32, stdout/stderr are reconfigured to UTF-8 for TTYs. New groups must be registered here **and** in the `set_gc_help` section lists. |
| `commands/` | Click UX per domain: `auth.py`, `issue.py` (10 subcommands), `pr.py` (13 subcommands), `compat.py`, `setup.py` | Commands resolve repo, build `Service(app_ctx.client())` + adapter, delegate, then shape output via `formatters.output_result`. Unimplemented-but-recognized flags raise `_pending_gh_compat("<key>")`; GitCode-impossible flags raise `unsupported("<CAPABILITY_KEY>")`. Both literals are test-policed (see the compat guide). |
| `adapters/` | gh-semantics → GitCode translation | See [adapters/AGENTS.md](adapters/AGENTS.md). |
| `services/` | Thin REST wrappers: `issues.py`, `pulls.py`, `users.py` | Path shapes are contract-tested against `tests/fixtures/gitcode-api-contracts/raw/`. Issue create/update post to `/repos/{owner}/issues` with `repo` in the JSON body (not the path) — unlike every other endpoint. `PullRequestService.list_comments` paginates internally at `per_page=100`; `diff()` requests `text/plain`. |
| `client.py` | `GitCodeClient`: httpx wrapper, `BASE_URL = "https://api.gitcode.com/api/v5/"` | Merges `access_token` into every request's query params, drops `None` param values; 30s timeout; 401 → `APIError` with a "run gc auth login" hint; other ≥400 → `APIError`; httpx transport errors → `NetworkError`. |
| `config.py` | Token persistence: `~/.config/gc/config.json` | Tests monkeypatch `CONFIG_DIR`/`CONFIG_PATH` module attributes (see `tests/conftest.py` `tmp_config_dir`). |
| `context.py` | `AppContext` dataclass (`token`, `repo`) with `client()` factory | Command tests replace `AppContext.client` via the `mock_app_context` fixture — keep the factory a single method. |
| `repo.py` | Repo string / remote URL parsing | `parse_repo_with_host` accepts `OWNER/REPO` and `HOST/OWNER/REPO`; host detection here feeds gh-proxy routing. |
| `errors.py` | `GCError` → `ConfigError`, `AuthError`, `RepoResolutionError`, `APIError(status_code)`, `NetworkError` | Only `GCError` subtypes get the graceful one-place exit handling in `cli.py`. |
| `formatters.py` | Output shaping: `--json` field filtering, `-q` jq, `-t` Go-template subset, list/detail renderers | `apply_jq` needs either the Python `jq` module or a `jq` binary on PATH — neither is a package dependency, so `--jq` can fail at runtime by design. Templates support only `{{.a.b}}`, `{{range .}}`, and `{{"\n"}}`. |
| `helptext.py` | gh-style grouped help rendering (`GCSectionGroup`, `set_gc_help` metadata) | Help text comes from attributes like `gc_command_sections`/`gc_examples` set via `set_gc_help`, not from docstrings alone. |
| `utils.py` | git subprocess helpers, issue/PR URL+number identifier parsing, `safe_echo` (encoding-safe) | `resolve_pr_arg` accepts number, URL, or branch (branch triggers an API lookup). |
| `cli_compat.py` | Shared command helpers: `--body`/`--body-file`/`--editor` resolution and `--fill[-first|-verbose]` git-log extraction | Despite the name, this is not the gh-compat registry — that is `compat/`. |
| `gh_proxy.py` + `commands/setup.py` | Optional `gh` dispatcher subsystem | See below. |
| `compat/` | gh-compatibility registry | See [compat/AGENTS.md](compat/AGENTS.md). |

## Layering rules (what must change together)

Adding or changing a user-facing flag typically touches four places in one PR:

1. The Click option in `commands/` (parsing, validation, help).
2. The translation in `adapters/` (new capability keys go in `adapters/capabilities.py` `CAPABILITY_MESSAGES`).
3. The registry row in `compat/entries.py` with the matching `pending_key` / `unsupported_key`.
4. Tests in `tests/unit/commands/` and/or `tests/unit/adapters/`.

`tests/unit/compat/test_registry_consistency.py` fails the build if any of these drift apart, so a partial change will not pass CI even if the new code itself works.

Output changes (`--json` field lists, `-t` templates, human formats) should extend the `gc_json_fields` metadata consumed by `helptext.py` and the normalization helpers in `commands/issue.py` / `commands/pr.py` (e.g. `_normalize_pr_fields` back-fills `mergedAt` from `merged_at`, `_normalize_closing_issue` maps `OPENED` → `OPEN` state).

## gh dispatcher subsystem (`gh_proxy.py`, `commands/setup.py`)

`gc setup gh-proxy` installs a `gh` shim next to nothing else — it never touches a real `gh` installation:

- Shim location: `~/.local/share/gc/gh-proxy/gh` (`%LOCALAPPDATA%\gc\gh-proxy\gh.cmd` on Windows), overridable with `GC_GH_PROXY_DIR`. The shim sets `GC_GH_SHIM` and execs `python -m gitcode_cli.gh_proxy`.
- Files without the managed marker (`Generated by gc setup gh-proxy`, `# >>> gc gh-proxy >>>`, `<!-- Generated by gc setup gh-proxy -->`) are never overwritten or removed — preserve this fail-safe when touching install/uninstall code.
- Routing (`gh_proxy.select_target`): `GC_GH_TARGET=gitcode|github` > host in explicit `-R`/`--repo` > `origin` host > default `github`. `gitcode.com` and `ssh.gitcode.com` are GitCode by default; `GC_GITCODE_HOSTS` adds more. `GC_REAL_GH` locates the native CLI when PATH discovery fails.
- GitCode-bound commands are fail-closed: `validate_gitcode_command` only accepts subcommands present (and not `not_in_cli`) in the compat registry — a command missing from the registry is an error, never a silent GitHub fallback.
- Dispatch to `gc` uses `os.execve` on POSIX (argument/stream/exit-status preserving) and `subprocess.call` on Windows, and exports `GC_GH_PROXY_ACTIVE=1` (consumed by `auth status` to print a proxy notice).
- `--configure` additionally writes a managed PATH block into the detected shell profile (`GC_GH_SHELL_PROFILE` override; zsh → `~/.zshenv`, bash → `~/.bash_profile` on macOS / `~/.bashrc` elsewhere, fish, PowerShell) and appends `gh-proxy-instructions.md` to the `instructions` array of `~/.config/opencode/opencode.json` (`GC_OPENCODE_CONFIG` override).

## Platform-dependent behavior

- Windows: use `gitcode` rather than `gc` (PowerShell alias collision); stdout/stderr are force-reconfigured to UTF-8 (`cli.py`); the shim is a `.cmd` batch file; proxy exec goes through `subprocess.call` instead of `execve`.
- `commands/setup.py` picks the shell profile file by `$SHELL` and `sys.platform` — changes here need coverage for more than one platform path.
