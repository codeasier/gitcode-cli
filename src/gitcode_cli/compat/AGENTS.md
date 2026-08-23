# AGENTS.md — `compat/` (gh-compatibility registry)

Parent scope: the `gitcode_cli` package ([../AGENTS.md](../AGENTS.md)). Build/test commands are documented at the repository root.

## What this directory owns

The authoritative registry of `gc` ↔ `gh` compatibility status, replacing the hand-maintained table from GitCode issue #68. It is metadata, not behavior: nothing here talks to the network or parses argv (with one exception — `gh_proxy` uses it as an allowlist, see below).

| File | Role |
|---|---|
| `_types.py` | `CompatStatus` enum (`implemented` / `pending` / `unsupported` / `not_in_cli`) and the frozen `CompatEntry` dataclass (`command`, `flag`, `status`, `note`, `pending_key`, `unsupported_key`, `gc_extension`, `aliases`). `flag is None` means the entry describes a whole subcommand. |
| `entries.py` | `ENTRIES` — the data, one `_e(...)` call per row, transcribed from issue #68. This is the only file you normally edit. |
| `registry.py` | Frozen aggregation/API: `iter_entries(groups=, statuses=)`, `statistics()`, `render_markdown_report()`. Do not mutate `_ENTRIES` — it is a `Final` tuple by design. |

## Status semantics

| Status | Runtime meaning |
|---|---|
| `implemented` | Click option exists and matches `gh` semantics (or a documented approximation). |
| `pending` | Option parses, but invoking it raises `_pending_gh_compat("<pending_key>")`. |
| `unsupported` | Option parses, but invoking it raises `unsupported("<unsupported_key>")`; the key must exist in `adapters/capabilities.py` `CAPABILITY_MESSAGES`. |
| `not_in_cli` | `gh` has it, `gc` does not — Click rejects the flag outright. |

## The lockstep contract (test-enforced)

`tests/unit/compat/test_registry_consistency.py` fails when any of these drift:

- every `pending` entry's `pending_key` appears as a literal `_pending_gh_compat("<key>")` call in `src/gitcode_cli/commands/*.py`, and vice versa;
- every `unsupported` entry's `unsupported_key` exists in `CAPABILITY_MESSAGES` and is raised via `unsupported(...)` in the command layer;
- every `implemented`/`pending`/`unsupported` flag is actually registered with Click, and every `not_in_cli` flag is absent;
- no duplicate `(command, flag)` pairs; at least 100 entries total (guards against accidental wipes).

Practical consequence: change `entries.py` in the same PR as the corresponding command/adapter code. A registry-only edit or a code-only edit will fail the unit suite.

## Consumers

| Consumer | How it uses the registry |
|---|---|
| `gc compat report [--stdout]`, `gc compat stats`, `gc compat list [--all] [--status ...]` (`commands/compat.py`) | Render the matrix as Markdown (issue #68 layout), JSON counts, or filtered rows. `gc compat report --stdout > COMPATIBILITY.md` regenerates the document — never hand-edit rendered output. |
| `gh_proxy.validate_gitcode_command` (`../gh_proxy.py`) | Fail-closed allowlist: a GitCode-targeted `gh` invocation is accepted only if its subcommand is registered here with a status other than `not_in_cli`. |
| `tests/unit/compat/test_compat_report.py` | Rendering/statistics checks. |
| `tests/unit/commands/test_cli_gh_compat.py` | Cross-checks the Click command tree against `tests/fixtures/gh-cli-compat/command_baseline.json` (a `gh --help` dump of gh 2.89.0) using `coverage.json` exclusion lists. |

When adding a top-level command group beyond `auth`/`issue`/`pr`, note that `render_markdown_report()` and `statistics()` hard-code the `("auth", "issue", "pr")` iteration — extend that tuple or the new group will silently vanish from reports, and `gh_proxy` will refuse its subcommands.
