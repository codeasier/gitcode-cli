# AGENTS.md

Guidance for coding agents working in this repository. Language: the repo's primary docs are English (`README.md`, `docs/en/`); `README.zh-CN.md`, `docs/zh-CN/`, and `ROADMAP.md` are Chinese translations/counterparts.

## What this repository is

This repository contains two independently installable Python distributions:

| Distribution | Source / configuration | Runtime boundary |
|---|---|---|
| `pygitcode` | `src/gitcode_cli/`, root `pyproject.toml` | Python >= 3.9; `click` and `httpx`; provides `gc` / `gitcode`, modeled after GitHub's `gh` CLI. |
| `codeasier-gitcode-mcp` | `packages/gitcode-mcp/` and its own `pyproject.toml` | Python >= 3.11; provides `gitcode-mcp` / `gitcode-clone`; separately versioned and currently pins the published `pygitcode==0.1.6`. |

A root editable install or root test run does not install or validate the MCP package. Do not assume MCP imports the sibling CLI checkout: its API layer subclasses `GitCodeClient` and reuses `IssueService` / `PullRequestService` from its installed dependency. Keep transport signatures compatible with downstream overrides when changing the CLI client.

## Architecture and data flow

The main CLI layering is below, with tests organized by layer (see `tests/AGENTS.md`). It is not a mandatory hop-by-hop path for every command: simple reads call services directly, and `pr audit` delegates to `audit.py`.

```
commands/*.py (Click UX, flag parsing, output shaping)
    → adapters/*.py (translate gh semantics into GitCode-compatible calls)
        → services/*.py (thin REST path/method wrappers)
            → client.py (httpx; injects access_token query param)
```

Two planes sit alongside that pipeline:

- `src/gitcode_cli/compat/` — the authoritative gc ↔ gh compatibility registry (metadata plane; also a routing allowlist for the gh proxy).
- `src/gitcode_cli/gh_proxy.py` + `src/gitcode_cli/commands/setup.py` — the optional `gh` dispatcher installed into user directories (`gc setup gh-proxy`).

See `src/gitcode_cli/AGENTS.md` for per-module responsibilities and invariants.

## Entry points and registration

| Entry point | Where defined | Notes |
|---|---|---|
| `gc`, `gitcode` console scripts | `pyproject.toml` `[project.scripts]` → `gitcode_cli.cli:main` | Both names are the same `main` group; `gitcode` exists because `gc` collides with PowerShell's `Get-Content`. |
| `python -m gitcode_cli.cli` | `__main__` guard in `src/gitcode_cli/cli.py` | This is how the gh proxy execs the real CLI (`gh_proxy.dispatch`). |
| `python -m gitcode_cli.gh_proxy` | `src/gitcode_cli/gh_proxy.py` | The installed `gh` shim execs this. |
| Command group registration | `main.add_command(...)` calls in `src/gitcode_cli/cli.py` | A new group must also be added to the `set_gc_help(...)` section lists on `main` (CORE/ADDITIONAL) or help output will be inconsistent. |

## Cross-cutting runtime behavior

- Token resolution order (`src/gitcode_cli/config.py`): `--token` flag > `GC_TOKEN` env var > `~/.config/gc/config.json` (written by `gc auth login`). Missing token raises `ConfigError`.
- Repo resolution (`src/gitcode_cli/repo.py`): explicit `-R [HOST/]OWNER/REPO` or `git remote get-url origin` (HTTPS, `ssh://`, and SCP-style SSH URLs are all parsed).
- Unhandled `GCError` subclasses are converted by `_GCMainGroup.invoke` (`src/gitcode_cli/cli.py`) to `error: ...` on stderr with exit code 1. Prefer typed errors; `pr audit` additionally collects per-PR errors and handles an authentication abort explicitly.
- The CLI client injects `access_token` into request query parameters. Keep credentials out of logs, fixtures, committed files and tool arguments; MCP has its own transport/authentication behavior, documented under `docs/gitcode/`.

## Build, run, test boundaries

| Task | Command | Evidence |
|---|---|---|
| Dev install | `pip install -e ".[dev]"` | `docs/en/development.md`, `.github/CONTRIBUTING.md` |
| Full CLI test suite (unit + contracts; excludes MCP) | `python -m pytest tests` | `pyproject.toml` `[tool.pytest.ini_options]` `testpaths = ["tests"]`; `tests/README.md` shows the maintainers' conda variant `conda run -n gitcode-cli python -m pytest tests` |
| Unit tests only | `python -m pytest tests/unit/` | This is what CI and pre-commit run — contract tests do **not** run in CI |
| Lint / format check | `python -m ruff check src/ tests/` and `python -m ruff format --check src/ tests/` | `ci.yml` lint job; config in `pyproject.toml` (line length 120, py39 target) |
| Type check | `python -m basedpyright src/` | `ci.yml` typecheck job; `[tool.basedpyright]` includes only `src` |
| CLI pre-commit checks (not MCP or contracts) | `pre-commit run --all-files` | `.pre-commit-config.yaml` (ruff, basedpyright, pytest unit with coverage gate) |

- The root pytest configuration's `addopts` enable `--cov=gitcode_cli --cov-fail-under=90` plus an HTML report, so CLI pytest runs using that configuration write `.coverage` and `htmlcov/` (both gitignored) and fail below 90% coverage.
- CLI CI (`ci.yml`) runs the unit suite on Python 3.9–3.13, plus a matrix aggregate, lint and typecheck jobs, on `main` pushes and PRs.

### MCP validation is separate

Use the package directory and its configuration, as `.github/workflows/gitcode-mcp.yml` does: install `.[dev]` there, run `python -I -m pytest -c pyproject.toml tests`, and use `python -m ruff check --config pyproject.toml .` / `python -m ruff format --check --config pyproject.toml .`. Clear inherited `PYTEST_ADDOPTS`; do not apply the CLI coverage gate or its Python 3.9 settings to MCP.

- MCP CI is path-filtered to `packages/gitcode-mcp/**`, `deploy/gitcode-mcp/**`, `docs/gitcode/**`, its workflow file and `.github/workflows/publish-mcp.yml`. A CLI-only or AGENTS-only PR does not automatically exercise it.
- Its Python 3.11–3.13 jobs lint, test, build wheel/sdist, clean-install both distributions and verify offline migration compatibility against the immutable legacy source. The separate named-volume job checks Compose volume reuse and rollback with synthetic state.
- Acceptance script paths are `packages/gitcode-mcp/scripts/migration_acceptance.py` and `volume_acceptance.py`; see [migration guidance](docs/gitcode/migration.md). CI acceptance is not a production deployment or live OAuth connection test. Do not use real credentials, production state or volumes for it.

## Release lifecycle and operational boundaries

- The CLI version is dynamic (`pyproject.toml` reads `gitcode_cli.__version__`, which is `0.0.0-dev` in-tree). Do not hand-bump it for releases: `.github/workflows/publish.yml` rewrites it from `v*` tags at build time, publishes to PyPI, and creates a GitHub Release.
- A `v*` tag fails to publish unless `CHANGELOG.md` contains a non-empty `## [x.y.z]` section for that version — the workflow validates it.
- `dev<commit-hash>` tags build `{base}.devYYYYMMDD+{hash}` versions to TestPyPI (`publish-dev.yml`), deriving the base from the latest `v*` tag.

- These `v*` / `dev*` tag workflows publish the CLI, not the MCP distribution. MCP publication preparation lives in `.github/workflows/publish-mcp.yml` for separately authorized `mcp-vX.Y.Z` tag creation. It reuses full MCP acceptance and requires an opt-in, pre-existing protected environment, independent reviewer, exact source/ref identity and the verified producer's immutable artifact ID/checksums. Manual runs validate only; publication remains disabled unless an operator separately configures the documented prerequisites. Package version and dependency pin stay independent. Follow the [MCP release guide](docs/gitcode/releases.md), [package guidance](packages/gitcode-mcp/README.md) and [deployment guidance](docs/gitcode/deployment.md); code review or CI does not authorize tagging, publishing, credential/security-setting changes or a production switch.

## Known misleading artifacts

- `CLAUDE.md` at the repo root is stale (it claims `tests/` is empty and predates `adapters/`, `compat/`, and the gh proxy). Trust `tests/README.md`, `docs/en/`, and these AGENTS.md files instead.

## Child guides

| Scope | File | What it owns |
|---|---|---|
| Python package | [src/gitcode_cli/AGENTS.md](src/gitcode_cli/AGENTS.md) | Per-module map, layer invariants, gh-proxy subsystem lifecycle, platform-dependent behavior |
| Compat registry | [src/gitcode_cli/compat/AGENTS.md](src/gitcode_cli/compat/AGENTS.md) | The gc ↔ gh status registry and its test-enforced lockstep contract |
| Adapter layer | [src/gitcode_cli/adapters/AGENTS.md](src/gitcode_cli/adapters/AGENTS.md) | gh-semantics translation, capability keys, `AdapterActionResult` protocol, pagination |
| CLI tests | [tests/AGENTS.md](tests/AGENTS.md) | Test layers, focusing commands, fixtures, coverage gate, conftest contracts |
| MCP package and operations | [packages/gitcode-mcp/README.md](packages/gitcode-mcp/README.md), [docs/gitcode/README.md](docs/gitcode/README.md) | Independent installation, authentication, migration and deployment boundaries |
