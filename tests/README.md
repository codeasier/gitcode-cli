# Tests

This test suite mirrors the `gc` architecture so failures can be isolated by layer.

## Layers

- `unit/test_cli.py` and `unit/commands/`: CLI and command behavior, including argument parsing, exit behavior, and command-to-adapter delegation.
- `unit/adapters/`: translation from `gh`-style command semantics into GitCode-compatible service calls, including degraded or approximated behavior.
- `unit/services/`: low-level GitCode API request construction, including HTTP method, path, and request payload filtering.
- `contracts/`: extracted-doc service contracts, strict HTTP transport checks, and in-process Issue/PR CLI golden flows against `tests/fixtures/gitcode-api-contracts/raw/`.
- `e2e/`: offline process smoke tests of the installed `gc` and `gitcode` console scripts, with isolated HOME/config/work directories and a credential-free child environment.
- `packaging/wheel_smoke.py`: the CI-only clean-wheel acceptance step, separate from the editable-install pytest suite.

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

The process harness resolves both console scripts only in the running interpreter's scripts directory and checks their installed `pygitcode` entrypoint metadata. It never resolves `gc` from the ambient PATH (which can select Graphviz or a shell alias). Each scenario runs outside the checkout. Child environments do not inherit tokens, proxy settings, Python paths or Git configuration; all config writes use the temporary HOME. The sanitized PATH retains the resolved Git executable's directory for Git for Windows; only the repository-inference scenario skips when Git is absent. A Python audit hook rejects network/DNS activity, with a separate guard test. No GitCode credentials or sandbox are needed.

The initial process scenarios cover root/auth/issue/PR help, installed version reporting, stdin login → config/token → logout, environment-over-config precedence, local repository/argument errors, unsupported output flags, exit codes and separate stdout/stderr. Tokens in these fixtures are synthetic. This is an **editable-install process smoke**, not clean-wheel acceptance, a mocked API golden flow, or full structured `gh` compatibility.

## Clean-wheel CI acceptance

Every Python 3.9–3.13 CLI matrix job also runs `packaging/wheel_smoke.py` after the ordinary suites. It builds one wheel from the exact checked-out `github.sha` (the tested merge SHA on PR runs), checks the tracked checkout is unchanged, and records the source SHA, wheel filename/SHA-256, normalized distribution version, package-file count, guard-probe count and per-entrypoint scenario count in a JSON log record. Wheel package bytes must match the checkout, and all Python source files must be present. This does not build a release or change the in-tree version.

Build and dependency installation are a distinct **network-enabled preparation phase**; they use the normal CI registry settings, not the offline claim. A fresh venv has no system site-packages, receives the exact wheel non-editably, and does not reuse the outer editable installation. Runtime checks verify `pyvenv.cfg`, distribution/entrypoint metadata, the installed wheel's `direct_url.json` hash, every installed package file and all loaded CLI module origins. Both absolute venv console-script paths must exist, be executable and select that venv's interpreter; there is no PATH or `python -m` substitute and no skip on missing entrypoints or a failed installation.

All runtime subprocesses run from a temporary directory outside the checkout, with a temporary HOME/config and an allowlisted environment that drops ambient credentials, proxies, `PYTHONPATH`, `PYTHONHOME` and inherited venv settings. An audit hook installed only into the disposable venv rejects Python socket/DNS operations and native-child launches, reports activation on each invocation, and is self-tested against DNS, TCP, UDP and child-process attempts. Even a swallowed denial fails the scenario. This is a guard against accidental external operations in trusted Python CLI tests, **not OS-level network isolation or a security sandbox for hostile Python/native code**. Preparation remains network-enabled.

For both `gc` and `gitcode`, the smoke checks help and exact version output, separate stdout/stderr and exit codes, missing-token behavior, synthetic stdin login → private temporary config → token output → logout, synthetic environment-token precedence, unknown-command errors and empty-token input. `contracts/test_clean_wheel_harness.py` tests the harness's fail-closed boundaries with synthetic files and mocked process results; the real build/install and guarded commands run in CI only. The existing 90% in-process coverage floor, lint/type checks, matrix aggregate, MCP jobs and dependency pin are unchanged. These packaging scenarios are not counted as CLI coverage, a provider-backed golden flow, sdist/platform acceptance, live GitCode access or complete gh parity.

## Remaining #124 acceptance boundaries

| Layer | Current evidence | Next acceptance gate |
| --- | --- | --- |
| Help compatibility | Existing gh 2.89.0 JSON baseline plus exact displayed command/flag/arity/summary checks for root, issue/pr groups and create commands on both entrypoints; explicit differences in the existing coverage JSON | Expand beyond these five commands and add independently sourced gh usage/argument/alias metadata and flag-description semantics; current gc usage/aliases are local invariants, not evidence of gh parity. |
| CLI behavior | Isolated no-network editable subprocess harness; clean-wheel installation and both entrypoints on Python 3.9–3.13 CI; ordered Issue create/view/close and PR create/view/edit/close CliRunner flows through real services/client and strict HTTP mocks | Wider mocked workflows/output/error coverage, recorded/provider-backed flows, sdist and additional OS coverage. These in-process mocks do not intercept subprocess HTTP. |
| API contracts | Extracted-doc service contracts plus real-client/HTTPX strict matching for Issue create/list and PR comment/review; unmatched requests and body/query/auth drift fail | Expand endpoint/workflow coverage and independently refresh upstream contracts; CLI query-token checks are not MCP OAuth or live account acceptance. |
| Recorded | Marker registered, no recording/replay suite yet | Define fixture provenance/versioning, refresh procedure and credential/body redaction before committing recordings. |
| Live/destructive | Markers registered only; explicitly excluded from ordinary PR CI | Obtain a dedicated authorized sandbox and credentials; define run IDs, concurrency isolation, `finally` cleanup/janitor and separate destructive opt-in. Only then add manual/nightly/release execution. |

`e2e`, `compat`, `recorded`, `live` and `destructive` markers are registered. Registering a marker does not implement or authorize its layer. There is no live workflow or live test in this batch; do not add one relying only on environment-variable presence. In particular, branch preparation may need separately authorized native Git credentials, and PR cleanup must not silently approve or merge. Keep #124 open until the remaining gates are delivered with evidence.

## In-process CLI golden-flow subset

`contracts/test_cli_golden_flows.py` joins the Click entrypoint, real adapters/services, `GitCodeClient` and HTTPX request preparation in one ordered scenario. It reuses the shared CLI/config/data fixtures and extracted endpoint docs. Only the client origin is redirected to a reserved `.invalid` host; `AppContext.client`, token resolution and all command/business logic remain real. Config/cwd are temporary and the environment token is synthetic. Strict RESPX matching rejects unregistered requests; a global request script also rejects reordered calls, unexpected payload/query/authentication changes, duplicate writes and incomplete flows. A negative CLI probe proves that unregistered HTTP raises rather than receiving implicit mock success.

The bounded scenarios cover Issue create from stdin → JSON view → close → human closed-state view → idempotent close, and PR create with one JSON readback → human view → title/body-file edit → JSON view → close → JSON closed-state view. They assert separate stdout/stderr, exit status, response-derived fields and exact request counts. Additional cases verify that a successful create followed by forbidden or wrong-identity readback reports partial completion without success JSON or a repeated write, a rejected close does not print success, and PR close rejects an unconfirmed response state.

These tests run in the existing `tests/contracts/` selection in ordinary CLI CI and the CLI job of source-compatibility CI. To retain the 90% coverage floor, use the complete offline command above rather than treating a single golden-flow file as full acceptance. The fixtures are synthetic, not provider recordings or a live state machine. This is an **in-process mocked API workflow**, not subprocess HTTP interception, recorded replay, live account acceptance or a complete human/JSON/jq/template/error matrix. The existing process and clean-wheel suites remain separate; recording provenance and live sandbox gates in the boundary matrix remain outstanding.

## Structured help subset

`e2e/help_compat/` parses the actual installed console scripts' help into command summaries, complete option alias → target mappings, boolean/value arity, usage and advertised aliases. It compares the first three fields against the independent `gh 2.89.0` snapshot in `command_baseline.json`, with reasoned differences under `coverage.json` → `help_surface`. Missing **and unexpected extra** commands/options fail; moving a short alias to another flag or changing a switch into a value option also fails. Parser regressions cover wrapped descriptions, color, product/binary naming, stale exceptions and intentional mutations. No new parallel compatibility manifest or live gh installation is required.

The selected scope is root, `issue`, `issue create`, `pr` and `pr create`, through both `gc` and `gitcode`. Local `new` aliases are also executed with `--help` and compared with their canonical create command. The fixture records absent root/subcommands as deferred, not as unsupported GitCode platform APIs. Existing broader one-directional unit checks remain intact.

The pinned gh snapshot does **not** contain usage, positional arguments or aliases. Accordingly, usage and aliases in `gc_invariants` are explicitly gc-only expectations, not reconstructed gh evidence. Its command summaries describe parent-menu entries: those displayed entries are compared, not the command's full introductory prose. Option metavar names are normalized to value-vs-switch arity; option descriptions and richer type semantics are not compared yet (for example, `issue create --template` uses a local file in gc rather than gh's named template). This subset does not establish complete gh compatibility or behavioral equivalence, and #124 stays open.

## Strict HTTP contract subset

`contracts/test_http_transport_contracts.py` keeps the real services, `GitCodeClient`, JSON serialization and HTTPX request preparation in the call path. A [strict RESPX router](https://lundberg.github.io/respx/api/#configuration) intercepts HTTPX before any network request: both `assert_all_mocked` and `assert_all_called` are explicitly enabled, with no pass-through routes. Tests use a reserved `.invalid` host and synthetic token, never ambient credentials. Registered methods/paths and allowed fields come from the existing extracted API fixtures, while callbacks assert exact query parameters, authentication placement, Accept/Content-Type and JSON payload/types. Negative guard cases prove that unregistered paths/methods and unexpected body/query/token values fail rather than silently receive mock success.

Coverage includes the owner-only Issue-create path with `repo` in the body, optional-field omission, PR general/inline `path` + integer `position` comments, the review `force: false` default and explicitly requested boolean value, list-query merging, HTTP 401/403/404/422 propagation and non-retry of synthetic timeout/connection failures. The review fixture documents only `force`: these checks do not claim support for GitHub review events, review text or a complete approval state machine. They verify CLI query-token behavior for Issue/PR endpoints, not MCP bearer/OAuth behavior or production permissions. Existing MagicMock service contracts remain useful and unchanged; this adds their missing serialized-HTTP boundary without replacing source-compatibility or live verification.

