# AGENTS.md

Guidance for coding agents working in this repository. Language: the repo's primary docs are English (`README.md`, `docs/en/`); `README.zh-CN.md`, `docs/zh-CN/`, and `ROADMAP.md` are Chinese translations/counterparts.

## What this repository is

`pygitcode` is a single Python package (src-layout) that provides the `gc` / `gitcode` CLI for GitCode (`https://api.gitcode.com/api/v5/`), modeled after GitHub's `gh` CLI. Runtime dependencies are only `click` and `httpx`. Python >= 3.9.

## Architecture and data flow

Request flow is a strict four-layer pipeline. Each layer is tested in isolation by a mirroring test layer (see `tests/AGENTS.md`):

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
- All `GCError` subclasses are caught once in `_GCMainGroup.invoke` (`src/gitcode_cli/cli.py`) and become `error: ...` on stderr with exit code 1. Command code raises typed errors; it does not print-and-exit itself.
- Every HTTP request carries the token as an `access_token` query parameter (GitCode's auth model — not a header).

## Build, run, test boundaries

| Task | Command | Evidence |
|---|---|---|
| Dev install | `pip install -e ".[dev]"` | `docs/en/development.md`, `.github/CONTRIBUTING.md` |
| Full test suite (unit + contracts) | `python -m pytest tests` | `pyproject.toml` `[tool.pytest.ini_options]` `testpaths = ["tests"]`; `tests/README.md` shows the maintainers' conda variant `conda run -n gitcode-cli python -m pytest tests` |
| Unit tests only | `python -m pytest tests/unit/` | This is what CI and pre-commit run — contract tests do **not** run in CI |
| Lint / format | `python -m ruff check src/ tests/` and `python -m ruff format src/ tests/` | `ci.yml` lint job; config in `pyproject.toml` (line length 120, py39 target) |
| Type check | `python -m basedpyright src/` | `ci.yml` typecheck job; `[tool.basedpyright]` includes only `src` |
| All checks at once | `pre-commit run --all-files` | `.pre-commit-config.yaml` (ruff, basedpyright, pytest unit with coverage gate) |

- pytest `addopts` always enable `--cov=gitcode_cli --cov-fail-under=90` plus an HTML report, so any pytest run writes `.coverage` and `htmlcov/` (both gitignored) and fails below 90% coverage.
- CI (`ci.yml`) runs the unit suite on Python 3.9–3.13, plus separate lint and typecheck jobs, on `main` pushes and PRs.

## Release lifecycle

- Version is dynamic (`pyproject.toml` reads `gitcode_cli.__version__`, which is `0.0.0-dev` in-tree). Do not hand-bump it for releases: `.github/workflows/publish.yml` rewrites it from `v*` tags at build time, publishes to PyPI, and creates a GitHub Release.
- A `v*` tag fails to publish unless `CHANGELOG.md` contains a non-empty `## [x.y.z]` section for that version — the workflow validates it.
- `dev<commit-hash>` tags build `{base}.devYYYYMMDD+{hash}` versions to TestPyPI (`publish-dev.yml`), deriving the base from the latest `v*` tag.

## Known misleading artifacts

- `CLAUDE.md` at the repo root is stale (it claims `tests/` is empty and predates `adapters/`, `compat/`, and the gh proxy). Trust `tests/README.md`, `docs/en/`, and these AGENTS.md files instead.

## Child guides

| Scope | File | What it owns |
|---|---|---|
| Python package | [src/gitcode_cli/AGENTS.md](src/gitcode_cli/AGENTS.md) | Per-module map, layer invariants, gh-proxy subsystem lifecycle, platform-dependent behavior |
| Compat registry | [src/gitcode_cli/compat/AGENTS.md](src/gitcode_cli/compat/AGENTS.md) | The gc ↔ gh status registry and its test-enforced lockstep contract |
| Adapter layer | [src/gitcode_cli/adapters/AGENTS.md](src/gitcode_cli/adapters/AGENTS.md) | gh-semantics translation, capability keys, `AdapterActionResult` protocol, pagination |
| Tests | [tests/AGENTS.md](tests/AGENTS.md) | Test layers, focusing commands, fixtures, coverage gate, conftest contracts |
