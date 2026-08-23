# AGENTS.md — `tests/`

Parent scope: repository root ([../AGENTS.md](../AGENTS.md)) for install commands and CI wiring. `README.md` in this directory explains the intent of the split; this guide adds the boundaries agents need when changing code.

## Layout mirrors the source layers

| Directory / file | Exercises | Typical focus command |
|---|---|---|
| `unit/test_cli.py`, `unit/test_cli_compat.py` | Root Click group, option wiring, helper functions | `python -m pytest tests/unit/test_cli.py` |
| `unit/commands/` | Command UX: parsing, guards, exit behavior, delegation to adapters | `python -m pytest tests/unit/commands/test_pr.py` |
| `unit/adapters/` | gh→GitCode translation, degradation, pagination | `python -m pytest tests/unit/adapters` |
| `unit/services/` | REST path/method/payload construction | `python -m pytest tests/unit/services` |
| `unit/compat/` | Registry consistency and report rendering | `python -m pytest tests/unit/compat` |
| `contracts/` | Service calls vs extracted GitCode API docs (fixtures below) | `python -m pytest tests/contracts` |
| Root-level `unit/test_*.py` | One file per core module: `test_client.py` (respx-mocked HTTP), `test_config.py`, `test_repo.py`, `test_gh_proxy.py`, `test_utils.py`, `test_formatters.py`, `test_errors.py`, `test_context.py` | `python -m pytest tests/unit/test_gh_proxy.py` |

`tests/README.md` and `docs/en/development.md` also show the maintainers' conda form (`conda run -n gitcode-cli python -m pytest ...`); CI and `.github/CONTRIBUTING.md` use the plain form. They are equivalent entry points.

## Boundaries and gotchas

- **CI never runs `tests/contracts/`.** Both `ci.yml` and the pre-commit pytest hook invoke `tests/unit/` only. The contract suite executes when you run the full suite (`python -m pytest tests`, via `testpaths` in `pyproject.toml`) — run it explicitly before touching `services/`.
- **Coverage gate is always on.** `pyproject.toml` `addopts` apply `--cov=gitcode_cli --cov-fail-under=90` (plus an HTML report writing `htmlcov/`, gitignored) to every pytest invocation, including single-file focus runs. CI adds `--cov-report=xml` and keeps the same 90% floor on the unit suite only.
- **`pythonpath = ["src"]`** is set for pytest, so tests import `gitcode_cli` without installing the package.
- **No test talks to the real API.** Command tests patch `AppContext.client` wholesale via the `mock_app_context` fixture in `conftest.py`; `test_client.py` uses `respx`; adapter/boundary tests use `MagicMock` services. Keep new command tests on `mock_app_context` (or `CliRunner` with it) rather than introducing real HTTP.

## Fixtures

| Path | Content | Consumed by |
|---|---|---|
| `fixtures/gitcode-api-contracts/raw/Issues/`, `fixtures/gitcode-api-contracts/raw/Pull Requests/` | Extracted GitCode API v5 endpoint docs (one JSON per method+path). Paths are formatted with `owner`/`repo` and compared after stripping the `/api/v5` prefix. | `contracts/test_gitcode_api_contracts.py` |
| `fixtures/gh-cli-compat/command_baseline.json` | Full `gh --help` command/flag tree of gh 2.89.0 | `unit/commands/test_cli_gh_compat.py` (drift detection between the `gc` Click tree and the `gh` baseline) |
| `fixtures/gh-cli-compat/coverage.json` | Per-command excluded flags and tracked subcommand selections for the baseline diff | same file; it fails if `coverage.json` references commands absent from the baseline |

`conftest.py` also provides shared data fixtures (`mock_issue_data`, `mock_pr_data`, list fixtures) and `tmp_config_dir`, which redirects token config to a temp dir by monkeypatching the `CONFIG_DIR`/`CONFIG_PATH` module attributes in `gitcode_cli.config` — new config-touching tests must use it to avoid reading the developer's real `~/.config/gc/config.json`.

## Where regressions usually land

The layer of a failure identifies the layer to fix: argument/exit-code problems in `unit/commands/` point at `src/gitcode_cli/commands/`; semantic drift (wrong filters, degraded behavior) in `unit/adapters/` points at `src/gitcode_cli/adapters/`; path/payload mismatches in `unit/services/` or `contracts/` point at `src/gitcode_cli/services/`; registry lockstep failures in `unit/compat/test_registry_consistency.py` mean `src/gitcode_cli/compat/entries.py` and the command code disagree (see [../src/gitcode_cli/compat/AGENTS.md](../src/gitcode_cli/compat/AGENTS.md)).
