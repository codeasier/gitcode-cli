# AGENTS.md — `tests/`

Parent scope: repository root ([../AGENTS.md](../AGENTS.md)) for install commands and CI wiring. `README.md` in this directory explains the intent of the split; this guide adds the boundaries agents need when changing code.

This directory tests the root CLI distribution only. MCP tests live at `packages/gitcode-mcp/tests/` and use that package's `pyproject.toml`; the root's `testpaths`, coverage floor and pre-commit hooks do not validate them. See the root guide's separate MCP CI section.

## Layout mirrors the source layers

| Directory / file | Exercises | Typical focus command |
|---|---|---|
| `unit/test_cli.py`, `unit/test_cli_compat.py` | Root Click group, option wiring, helper functions | `python -m pytest tests/unit/test_cli.py` |
| `unit/commands/` | Command UX: parsing, guards, exit behavior, delegation to adapters | `python -m pytest tests/unit/commands/test_pr.py` |
| `unit/adapters/` | gh→GitCode translation, degradation, pagination | `python -m pytest tests/unit/adapters` |
| `unit/services/` | REST path/method/payload construction | `python -m pytest tests/unit/services` |
| `unit/compat/` | Registry consistency and report rendering | `python -m pytest tests/unit/compat` |
| `contracts/` | Service calls vs extracted API docs; strict serialized-HTTP subset through real services/client and RESPX | `python -m pytest tests/contracts` |
| `e2e/` | Installed-entrypoint subprocess smoke in isolated HOME/env/work directories; no API access | Install the checkout, then use the complete offline command in `README.md` to retain the coverage gate |
| Root-level `unit/test_*.py` | One file per core module: `test_client.py` (respx-mocked HTTP), `test_config.py`, `test_repo.py`, `test_gh_proxy.py`, `test_utils.py`, `test_formatters.py`, `test_errors.py`, `test_context.py`, `test_audit.py`, `test_helptext.py` | `python -m pytest tests/unit/test_gh_proxy.py` |

`tests/README.md` and `docs/en/development.md` also show the maintainers' conda form (`conda run -n gitcode-cli python -m pytest ...`); CI and `.github/CONTRIBUTING.md` use the plain form. They are equivalent entry points.

## Boundaries and gotchas

- **`ci.yml` runs unit, contracts and non-live e2e; pre-commit still runs unit only.** The Python 3.9–3.13 CLI matrix uses strict markers and excludes `live`/`destructive`. The separate `gitcode-mcp-services.yml` CLI job invokes `tests/unit/` and `tests/contracts/` with the same 90% coverage floor. Registered recorded/live markers are plans, not implemented or authorized execution layers.
- **CLI coverage gate is enabled by default.** `pyproject.toml` `addopts` apply `--cov=gitcode_cli --cov-fail-under=90` (plus an HTML report writing `htmlcov/`, gitignored) to CLI pytest invocations using this configuration, including single-file focus runs. CI adds `--cov-report=xml` and keeps the same 90% floor. Child-process smoke execution is not claimed as measured coverage; retain the in-process suites when checking that floor.
- **`pythonpath = ["src"]`** is set for pytest, so tests import `gitcode_cli` without installing the package.
- **Keep CLI tests off the real API.** Command tests patch `AppContext.client` wholesale via the `mock_app_context` fixture in `conftest.py`; `test_client.py` uses `respx`; adapter/boundary tests use `MagicMock` services. Keep new command tests on `mock_app_context` (or `CliRunner` with it) rather than introducing real HTTP.
- **Strict HTTP contracts still stay offline.** `contracts/test_http_transport_contracts.py` uses real services and `GitCodeClient`, but an explicitly strict RESPX router intercepts HTTPX at a reserved `.invalid` origin. Both unmatched requests and unused routes fail; callbacks verify serialized paths, queries, headers and JSON against extracted fixtures. Keep its synthetic token and no-pass-through policy. CLI query authentication is not evidence of MCP OAuth or live permissions.
- **Process e2e is a separate boundary.** `e2e/conftest.py` resolves installed console scripts from this interpreter's scripts directory, not ambient PATH. Its allowlisted child environment and temporary HOME must remain credential-free; the audit hook rejects Python network/DNS attempts. Never assume a parent `respx` mock protects subprocesses. These tests require an installed checkout and do not establish clean-wheel or structured help-compatibility acceptance.
- **Request overrides are a compatibility contract.** `unit/services/test_repos.py` and `test_files.py` use tokenless clients with the original `request` signature to catch service credential coupling or new keyword arguments. `unit/test_client.py` separately verifies CLI repository-only authentication; command tests cover every target source, foreign-host rejection, and secret-safe rename output.
- **MCP has independent CI and fixtures.** Its path-filtered workflow runs Python 3.11–3.13 package tests and offline migration/clean-install checks, plus synthetic Compose named-volume takeover/rollback. A green CLI run is not evidence of MCP compatibility. The separate source-compatibility workflow additionally replaces only the installed CLI with the current checkout, verifies client/service hashes, and runs the complete MCP suite plus explicit `packages/gitcode-mcp/tests_source/` and checkout-only `tests_checkout/` contracts on Python 3.11–3.13. Unreleased producer methods belong only in `tests_checkout/`, never in suites selected against published artifacts. The ordinary pinned-dependency MCP test selection remains `tests/` only; a separate six-job artifact matrix installs the actual published `pygitcode==0.1.7` wheel and sdist on Python 3.11–3.13, verifies their hashes and installed origin, then runs both `tests/` and `tests_source/` in isolation. Changes to shared transport/service interfaces need explicit cross-package validation against both the production dependency and proposed source; never substitute production credentials or OAuth state.

## Fixtures

| Path | Content | Consumed by |
|---|---|---|
| `fixtures/gitcode-api-contracts/raw/Issues/`, `fixtures/gitcode-api-contracts/raw/Pull Requests/` | Extracted GitCode API v5 endpoint docs (one JSON per method+path). Service-only checks strip the `/api/v5` prefix; transport checks assert the complete serialized path. | `contracts/test_gitcode_api_contracts.py`, `contracts/test_http_transport_contracts.py` |
| `fixtures/gh-cli-compat/command_baseline.json` | Full `gh --help` command/flag tree of gh 2.89.0 | `unit/commands/test_cli_gh_compat.py` (drift detection between the `gc` Click tree and the `gh` baseline) |
| `fixtures/gh-cli-compat/coverage.json` | Per-command excluded flags and tracked subcommand selections for the baseline diff | same file; it fails if `coverage.json` references commands absent from the baseline |

`conftest.py` also provides shared data fixtures (`mock_issue_data`, `mock_pr_data`, list fixtures) and `tmp_config_dir`, which redirects token config to a temp dir by monkeypatching the `CONFIG_DIR`/`CONFIG_PATH` module attributes in `gitcode_cli.config` — new config-touching tests must use it to avoid reading the developer's real `~/.config/gc/config.json`.

## Where regressions usually land

The layer of a failure identifies the layer to fix: argument/exit-code problems in `unit/commands/` point at `src/gitcode_cli/commands/`; semantic drift (wrong filters, degraded behavior) in `unit/adapters/` points at `src/gitcode_cli/adapters/`; path/payload mismatches in `unit/services/` or `contracts/` point at `src/gitcode_cli/services/`; registry lockstep failures in `unit/compat/test_registry_consistency.py` mean `src/gitcode_cli/compat/entries.py` and the command code disagree (see [../src/gitcode_cli/compat/AGENTS.md](../src/gitcode_cli/compat/AGENTS.md)).

