# Contributing to pygitcode

Thanks for your interest in contributing! This guide will help you get started.

## Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/gitcode-cli.git
cd gitcode-cli

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Install pre-commit hooks
pre-commit install
```

## Development Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
   Use descriptive branch names: `feature/`, `fix/`, `docs/`, `refactor/`, `ci/`.

2. **Make your changes** and commit with clear messages:
   ```bash
   git commit -m "feat: add gc repo view command"
   ```
   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation
   - `refactor:` code refactor
   - `test:` adding/updating tests
   - `ci:` CI/CD changes
   - `chore:` maintenance tasks

3. **Run checks** before pushing:
   ```bash
   # All checks at once
   pre-commit run --all-files

   # Or individually
   python -m pytest tests/unit/ --cov=gitcode_cli
   python -m ruff check src/ tests/
   python -m ruff format src/ tests/
   python -m basedpyright src/
   ```

4. **Push and open a Pull Request** against `main`.

## Code Style

- **Formatter**: [black](https://black.readthedocs.io/) + [ruff format](https://docs.astral.sh/ruff/), line-length 120
- **Linter**: [ruff](https://docs.astral.sh/ruff/) with rules: E, W, F, I, N, UP, B, C4, SIM, ARG, PL
- **Type checker**: [basedpyright](https://basedpyright.readthedocs.io/) in standard mode
- **Python version**: >= 3.9

## Testing

- All code must have test coverage >= 90%.
- Tests live in `tests/unit/`, mirroring the `src/gitcode_cli/` structure.
- Use `pytest` with `pytest-mock` for mocking and `respx` for HTTP mocking.
- Run tests: `python -m pytest tests/unit/`
- Run with coverage: `python -m pytest tests/unit/ --cov=gitcode_cli --cov-fail-under=90`

## Architecture

```
src/gitcode_cli/
├── cli.py            # Click entry point (gc command)
├── cli_compat.py     # Command aliases (ls→list, new→create)
├── client.py         # httpx HTTP client wrapper
├── config.py         # Token/config parsing
├── context.py        # AppContext dataclass
├── errors.py         # Exception hierarchy
├── formatters.py     # Output formatting (table, JSON, template)
├── repo.py           # Repository URL parsing
├── utils.py          # Utility functions
├── commands/         # Click subcommands
│   ├── auth.py       # gc auth login
│   ├── issue.py      # gc issue *
│   └── pr.py         # gc pr *
└── services/         # GitCode API wrappers
    ├── issues.py     # Issue CRUD + comments
    └── pulls.py      # PR CRUD + merge + comments + reviews
```

**Layering**: `commands` -> `services` -> `client`. Commands handle CLI parsing, services handle API logic, client handles HTTP transport.

## Reporting Issues

- **Bug reports**: Use the [Bug Report](https://github.com/codeasier/gitcode-cli/issues/new?template=bug_report.yml) template.
- **Feature requests**: Use the [Feature Request](https://github.com/codeasier/gitcode-cli/issues/new?template=feature_request.yml) template.
- **Questions**: Use the [Question](https://github.com/codeasier/gitcode-cli/issues/new?template=question.yml) template.

## Pull Request Guidelines

- Keep PRs focused on a single change.
- Include tests for new functionality.
- Update documentation (README, docstrings) if needed.
- Ensure all CI checks pass (tests on Python 3.9-3.13, ruff lint/format, basedpyright).
- Follow the PR template when submitting.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
