# Development

## Setup

```bash
git clone https://github.com/codeasier/gitcode-cli.git
cd gitcode-cli
pip install -e ".[dev]"
```

## Run tests

Run the full suite:

```bash
conda run -n gitcode-cli python -m pytest tests
```

Run one layer:

```bash
conda run -n gitcode-cli python -m pytest tests/unit/commands
conda run -n gitcode-cli python -m pytest tests/unit/adapters
conda run -n gitcode-cli python -m pytest tests/unit/services
conda run -n gitcode-cli python -m pytest tests/contracts
```

For test layout and intent, see [tests/README.md](../tests/README.md).

## Static checks

```bash
python -m ruff check src/ tests/
python -m ruff format src/ tests/
python -m basedpyright src/
```
