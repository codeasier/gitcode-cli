# AGENTS.md

Guidance for coding agents working in this repository. Language: the repo's primary docs are English (`README.md`, `docs/en/`); `README.zh-CN.md`, `docs/zh-CN/`, and `ROADMAP.md` are Chinese translations/counterparts.

## What this repository is

This repository contains two independently installable Python distributions:

| Distribution | Source / configuration | Runtime boundary |
|---|---|---|
| `pygitcode` | `src/gitcode_cli/`, root `pyproject.toml` | Python >= 3.9; `click` and `httpx`; provides `gc` / `gitcode`, modeled after GitHub's `gh` CLI. |
| `codeasier-gitcode-mcp` | `packages/gitcode-mcp/` and its own `pyproject.toml` | Python >= 3.11; provides `gitcode-mcp` / `gitcode-clone`; separately versioned and currently pins the published `pygitcode==0.1.7`. |

A root editable install or root test run does not install or validate the MCP package. Do not assume MCP imports the sibling CLI checkout: its API layer subclasses `GitCodeClient` and reuses `IssueService` / `PullRequestService` / `FileService` / `RepoService` from its installed dependency. MCP retains its stricter file-path validation, content/result policies and bounded bearer-only transport; services receive decoded paths and quote them once. Keep transport signatures compatible with downstream overrides when changing the CLI client.

## Architecture and data flow

The main CLI layering is below, with tests organized by layer (see `tests/AGENTS.md`). It is not a mandatory hop-by-hop path for every command: simple reads call services directly, and `pr audit` delegates to `audit.py`.

```
commands/*.py (Click UX, flag parsing, output shaping)
    → adapters/*.py (translate gh semantics into GitCode-compatible calls)
        → services/*.py (thin REST path/method wrappers)
            → client.py (httpx; owns CLI query/header authentication)
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
- Repo resolution (`src/gitcode_cli/repo.py`): explicit `-R [HOST/]OWNER/REPO` or `git remote get-url origin` (HTTPS, `ssh://`, and SCP-style SSH URLs are all parsed). `gc repo` additionally validates the effective positional, command/global `-R`, or origin host before any API call; foreign hosts and invalid path segments fail closed.
- Unhandled `GCError` subclasses are converted by `_GCMainGroup.invoke` (`src/gitcode_cli/cli.py`) to `error: ...` on stderr with exit code 1. Prefer typed errors; `pr audit` additionally collects per-PR errors and handles an authentication abort explicitly.
- The CLI client injects `access_token` into request query parameters and adds `private-token` only for the repository endpoint/method combinations in `client._requires_private_token`. Shared services never read or assemble credentials; keep the public request/helper signatures compatible with MCP overrides. Keep credentials out of logs, fixtures, committed files and tool arguments; MCP has its own transport/authentication behavior, documented under `docs/gitcode/`.

## Build, run, test boundaries

| Task | Command | Evidence |
|---|---|---|
| Dev install | `pip install -e ".[dev]"` | `docs/en/development.md`, `.github/CONTRIBUTING.md` |
| Full CLI test suite (unit + contracts + offline process e2e; excludes MCP) | `python -m pytest tests` | First install the checkout with the same interpreter; `tests/e2e/` resolves installed console scripts. `tests/README.md` also shows the maintainers' conda variant. |
| Unit tests only | `python -m pytest tests/unit/` | Pre-commit selects unit tests; `ci.yml` selects unit + contracts + non-live e2e, and the separate source-compatibility workflow runs unit + contracts. |
| Lint / format check | `python -m ruff check src/ tests/` and `python -m ruff format --check src/ tests/` | `ci.yml` lint job; config in `pyproject.toml` (line length 120, py39 target) |
| Type check | `python -m basedpyright src/` | `ci.yml` typecheck job; `[tool.basedpyright]` includes only `src` |
| CLI pre-commit checks (not MCP or contracts) | `pre-commit run --all-files` | `.pre-commit-config.yaml` (ruff, basedpyright, pytest unit with coverage gate) |

- The root pytest configuration's `addopts` enable `--cov=gitcode_cli --cov-fail-under=90` plus an HTML report, so CLI pytest runs using that configuration write `.coverage` and `htmlcov/` (both gitignored) and fail below 90% coverage.
- CLI CI (`ci.yml`) runs unit, contracts and offline e2e on Python 3.9–3.13, explicitly excluding `live` and `destructive`, plus a matrix aggregate, lint and typecheck jobs, on `main` pushes and PRs. Process smoke tests are not clean-wheel, live or full gh-compatibility acceptance; see `tests/README.md` for remaining #124 gates.

### MCP validation is separate

Use the package directory and its configuration, as `.github/workflows/gitcode-mcp.yml` does: install `.[dev]` there, run `python -I -m pytest -c pyproject.toml tests`, and use `python -m ruff check --config pyproject.toml .` / `python -m ruff format --check --config pyproject.toml .`. Clear inherited `PYTEST_ADDOPTS`; do not apply the CLI coverage gate or its Python 3.9 settings to MCP.

- The published-dependency MCP CI (`gitcode-mcp.yml`) is path-filtered to `packages/gitcode-mcp/**`, `deploy/gitcode-mcp/**`, `docs/gitcode/**`, its workflow file and `.github/workflows/publish-mcp.yml`. A CLI-only or AGENTS-only PR does not automatically exercise it.
- `gitcode-mcp-services.yml` separately gates CLI source/service changes: Python 3.11–3.13 jobs install the MCP dependencies, replace only the CLI distribution from the checkout with `--no-deps`, verify every installed client/service file hash, then run the full MCP suite plus explicitly selected `tests_source/` shared-service and `tests_checkout/` unreleased-producer contracts. The normal pinned-dependency MCP job still selects only `tests/`. This is a compatibility probe, not a change to the published MCP pin. Its Python 3.13 CLI job runs `tests/unit/` plus `tests/contracts/` with the existing 90% coverage floor.
- The published CLI artifact matrix independently installs the actual `pygitcode==0.1.7` wheel and sdist on Python 3.11–3.13, checks their hashes and installed origin, and runs both `tests/` and `tests_source/` from an isolated working directory. This does not replace either the normal MCP package acceptance or the forward-looking checkout compatibility probe.
- The published-dependency workflow's Python 3.11–3.13 jobs lint, test, build wheel/sdist, clean-install both distributions and verify offline migration compatibility against the immutable legacy source. The separate named-volume job checks Compose volume reuse and rollback with synthetic state.
- Acceptance script paths are `packages/gitcode-mcp/scripts/migration_acceptance.py` and `volume_acceptance.py`; see [migration guidance](docs/gitcode/migration.md). The immutable legacy seed remains MCP 0.3.0 with `pygitcode==0.1.6`; candidate checks require `pygitcode==0.1.7`. These roles cannot be inferred from the MCP version, which remains 0.3.0. CI acceptance is not a production deployment or live OAuth connection test. Do not use real credentials, production state or volumes for it.

## Release lifecycle and operational boundaries

- The CLI version is dynamic (`pyproject.toml` reads `gitcode_cli.__version__`, which is `0.0.0-dev` in-tree). Do not hand-bump it for releases: `.github/workflows/publish.yml` rewrites it from `v*` tags at build time, publishes to PyPI, and creates a GitHub Release.
- A `v*` tag fails to publish unless `CHANGELOG.md` contains a non-empty `## [x.y.z]` section for that version — the workflow validates it.
- `dev<commit-hash>` tags build `{base}.devYYYYMMDD+{hash}` versions to TestPyPI (`publish-dev.yml`), deriving the base from the latest `v*` tag.

- These `v*` / `dev*` tag workflows publish the CLI, not the MCP distribution. MCP publication preparation lives in `.github/workflows/publish-mcp.yml` for separately authorized `mcp-vX.Y.Z` tag creation. It reuses full MCP acceptance and requires an opt-in, pre-existing protected environment, independent reviewer, exact source/ref identity and the verified producer's immutable artifact ID/checksums. Manual runs validate only; publication remains disabled unless an operator separately configures the documented prerequisites. Package version and dependency pin stay independent. Follow the [MCP release guide](docs/gitcode/releases.md), [package guidance](packages/gitcode-mcp/README.md) and [deployment guidance](docs/gitcode/deployment.md); code review or CI does not authorize tagging, publishing, credential/security-setting changes or a production switch.

## Known misleading artifacts

- `CLAUDE.md` is a partial legacy overview and does not map all adapter, compatibility-registry, or dispatcher modules. Use `tests/README.md`, `docs/en/`, and these AGENTS.md files for the complete module and validation boundaries.

## Child guides

| Scope | File | What it owns |
|---|---|---|
| Python package | [src/gitcode_cli/AGENTS.md](src/gitcode_cli/AGENTS.md) | Per-module map, layer invariants, gh-proxy subsystem lifecycle, platform-dependent behavior |
| Compat registry | [src/gitcode_cli/compat/AGENTS.md](src/gitcode_cli/compat/AGENTS.md) | The gc ↔ gh status registry and its test-enforced lockstep contract |
| Adapter layer | [src/gitcode_cli/adapters/AGENTS.md](src/gitcode_cli/adapters/AGENTS.md) | gh-semantics translation, capability keys, `AdapterActionResult` protocol, pagination |
| CLI tests | [tests/AGENTS.md](tests/AGENTS.md) | Test layers, focusing commands, fixtures, coverage gate, conftest contracts |
| MCP package and operations | [packages/gitcode-mcp/README.md](packages/gitcode-mcp/README.md), [docs/gitcode/README.md](docs/gitcode/README.md) | Independent installation, authentication, migration and deployment boundaries |

