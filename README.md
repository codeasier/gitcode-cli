# pygitcode

> A CLI tool for [GitCode](https://gitcode.com/) (`api.gitcode.com`), modeled after GitHub CLI (`gh`).

[![PyPI](https://img.shields.io/pypi/v/pygitcode)](https://pypi.org/project/pygitcode/)
[![Python](https://img.shields.io/pypi/pyversions/pygitcode)](https://pypi.org/project/pygitcode/)
[![License](https://img.shields.io/pypi/l/pygitcode)](https://github.com/yourusername/pygitcode/blob/main/LICENSE)
[![Tests](https://github.com/yourusername/pygitcode/workflows/Tests/badge.svg)](https://github.com/yourusername/pygitcode/actions)

## Installation

```bash
pip install pygitcode
```

This exposes the `gc` command in your shell.

## Quick Start

### Authentication

```bash
# Login with your GitCode personal access token
gc auth login

# Or set environment variable
export GC_TOKEN=your_token_here
```

### Issues

```bash
# List issues
gc issue list

# View an issue
gc issue view 42

# Create an issue (title/body are optional -- you'll be prompted)
gc issue create -t "Bug report" -b "Something is broken"

# Close / reopen / edit / delete
gc issue close 42
gc issue reopen 42
gc issue edit 42 -t "Updated title"
gc issue delete 42

# Comment on an issue
gc issue comment 42 -b "Thanks for the report!"
```

### Pull Requests

```bash
# List PRs
gc pr list

# View a PR (by number, URL, or branch name)
gc pr view 42
gc pr view https://gitcode.com/owner/repo/pulls/42
gc pr view feature-branch

# Create a PR (auto-detects current branch and default base)
gc pr create -t "Add new feature"

# Close / merge / reopen / edit
gc pr close 42 -c "Closing as stale"
gc pr merge 42 -s
gc pr reopen 42
gc pr edit 42 -t "New title"

# Comment / review / diff / checkout
gc pr comment 42 -b "LGTM"
gc pr review 42 --approve
gc pr diff 42
gc pr checkout 42
```

### Global Options

```bash
# Use a different repo without cd-ing into it
gc issue list -R owner/repo

# Output as JSON with field selection
gc issue list --json number,title,state

# Filter with jq
gc issue list -q '.[] | select(.state == "open")'

# Format with Go-style templates
gc issue list -t '{{.number}} {{.title}}'

# Open in browser
gc issue view 42 -w
```

## Alignment with `gh` CLI

`pygitcode` aims to be as familiar as possible to `gh` users:

- Short options: `-a`, `-b`, `-l`, `-s`, `-t`, `-w`, etc.
- Optional required fields with interactive prompts
- Supports `<number>`, `<url>`, and `<branch>` identifiers for PR commands
- `--json fields`, `-q jq`, `-t template` output formatting
- Command aliases: `ls` → `list`, `new` → `create`

## Development

```bash
# Clone
git clone https://github.com/yourusername/pygitcode.git
cd pygitcode

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run all checks manually
pre-commit run --all-files

# Or run individually
python -m pytest tests/unit/ --cov=gitcode_cli
python -m ruff check src/ tests/
python -m ruff format src/ tests/
python -m basedpyright src/
```

## License

MIT
