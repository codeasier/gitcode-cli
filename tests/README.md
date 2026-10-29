# Tests

This test suite mirrors the `gc` architecture so failures can be isolated by layer.

## Layers

- `unit/test_cli.py` and `unit/commands/`: CLI and command behavior, including argument parsing, exit behavior, and command-to-adapter delegation.
- `unit/adapters/`: translation from `gh`-style command semantics into GitCode-compatible service calls, including degraded or approximated behavior.
- `unit/services/`: low-level GitCode API request construction, including HTTP method, path, and request payload filtering.
- `contracts/`: contract checks against extracted GitCode API docs under `tests/fixtures/gitcode-api-contracts/raw/`.
- `e2e/`: offline process smoke tests of the installed `gc` and `gitcode` console scripts, with isolated HOME/config/work directories and a credential-free child environment.

## Why this split exists

The CLI aims to feel `gh`-compatible while still speaking GitCode's API correctly. Keeping tests split by layer makes it easier to tell whether a regression comes from command UX, adapter translation, service request construction, or API contract drift.

## Running tests

Run the full suite:

```bash
conda run -n gitcode-cli python -m pytest tests
```

Run one layer:

```bash
conda run -n gitcode-cli python -m pytest tests/unit/adapters
conda run -n gitcode-cli python -m pytest tests/unit/services
conda run -n gitcode-cli python -m pytest tests/contracts
```

## Offline process tests and PR gate

Install the checkout into the interpreter that runs pytest before selecting `tests/e2e/`:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/unit/ tests/contracts/ tests/e2e/ -m "not live and not destructive" --strict-markers
```

The normal CLI CI runs this selection on Python 3.9–3.13, preserving the 90% CLI coverage floor, lint, type checks and matrix aggregate. The coverage floor primarily measures the in-process unit/contract suite; child process execution is not claimed as measured coverage. Pre-commit still selects unit tests only. MCP has separate package and source-compatibility workflows; these CLI tests do not replace them.

The process harness resolves both console scripts only in the running interpreter's scripts directory and checks their installed `pygitcode` entrypoint metadata. It never resolves `gc` from the ambient PATH (which can select Graphviz or a shell alias). Each scenario runs outside the checkout. Child environments do not inherit tokens, proxy settings, Python paths or Git configuration; all config writes use the temporary HOME. A Python audit hook rejects network/DNS activity, with a separate guard test. No GitCode credentials or sandbox are needed.

The initial process scenarios cover root/auth/issue/PR help, installed version reporting, stdin login → config/token → logout, environment-over-config precedence, local repository/argument errors, unsupported output flags, exit codes and separate stdout/stderr. Tokens in these fixtures are synthetic. This is an **editable-install process smoke**, not clean-wheel acceptance, a mocked API golden flow, or full structured `gh` compatibility.

## Remaining #124 acceptance boundaries

| Layer | Current evidence | Next acceptance gate |
| --- | --- | --- |
| Help compatibility | Existing gh 2.89.0 JSON baseline/coverage plus command/flag unit checks; process smoke for both names | Extend the existing JSON schema/parser to compare root/group/subcommand usage, arguments, aliases and unexpected differences. Do not create a parallel manifest or call substring smoke structured parity. |
| CLI behavior | Isolated no-network subprocess harness; existing CliRunner command/unit coverage | Strict mocked/recorded issue and PR golden flows, full output/error matrix, and isolated wheel installation for both entrypoints. A parent-process HTTP mock does not intercept subprocess HTTP. |
| API contracts | Extracted-doc service contracts now in every CLI PR matrix; separate respx client units | Add real-transport strict request matching (including unregistered-request failure) for high-risk paths, payloads and authentication. |
| Recorded | Marker registered, no recording/replay suite yet | Define fixture provenance/versioning, refresh procedure and credential/body redaction before committing recordings. |
| Live/destructive | Markers registered only; explicitly excluded from ordinary PR CI | Obtain a dedicated authorized sandbox and credentials; define run IDs, concurrency isolation, `finally` cleanup/janitor and separate destructive opt-in. Only then add manual/nightly/release execution. |

`e2e`, `compat`, `recorded`, `live` and `destructive` markers are registered. Registering a marker does not implement or authorize its layer. There is no live workflow or live test in this batch; do not add one relying only on environment-variable presence. In particular, branch preparation may need separately authorized native Git credentials, and PR cleanup must not silently approve or merge. Keep #124 open until the remaining gates are delivered with evidence.

