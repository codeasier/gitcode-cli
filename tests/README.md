# Tests

This test suite mirrors the `gc` architecture so failures can be isolated by layer.

## Layers

- `unit/test_cli.py` and `unit/commands/`: CLI and command behavior, including argument parsing, exit behavior, and command-to-adapter delegation.
- `unit/adapters/`: translation from `gh`-style command semantics into GitCode-compatible service calls, including degraded or approximated behavior.
- `unit/services/`: low-level GitCode API request construction, including HTTP method, path, and request payload filtering.
- `contracts/`: contract checks against extracted GitCode API docs under `.claude/skills/gitcode-docs/output/gitcode-api/raw/`.

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
