# pygitcode

> A CLI tool for [GitCode](https://gitcode.com/) (`api.gitcode.com`), modeled after GitHub CLI (`gh`).

[![PyPI](https://img.shields.io/pypi/v/pygitcode)](https://pypi.org/project/pygitcode/)
[![Python](https://img.shields.io/pypi/pyversions/pygitcode)](https://pypi.org/project/pygitcode/)
[![License](https://img.shields.io/pypi/l/pygitcode)](https://github.com/codeasier/gitcode-cli/blob/main/LICENSE)

English | [中文](README.zh-CN.md)

For agent-assisted setup, usage, upgrades, or troubleshooting, read [docs/en/USING_WITH_AGENT.md](docs/en/USING_WITH_AGENT.md) first.

## Installation

```bash
pip install pygitcode
```

This exposes both `gc` and `gitcode` commands in your shell.

To optionally route existing `gh` commands between GitCode and GitHub, install and configure the managed proxy:

```bash
gc setup gh-proxy --configure
```

The command installs the shim, adds a managed shell `PATH` block, and registers OpenCode instructions that teach agents to try the dispatcher before API fallbacks. Restart OpenCode afterward. The proxy sends GitCode repositories to `gc`, sends GitHub or unknown contexts to the native `gh`, and refuses unsupported commands when the target is GitCode. See [the compatibility notes](docs/en/gh-compatibility.md#optional-gh-proxy) for routing controls and uninstall instructions.

## Quick Start

If you already know GitHub CLI (`gh`), you can start with the same familiar flows:

```bash
gc auth login
gc issue list
gc issue view 42
gc pr list
gc pr create --fill
gc pr merge 42 --squash
gc repo view owner/repo
gc repo clone owner/repo
```

Use `gitcode` instead of `gc` on Windows PowerShell because `gc` is a built-in alias for `Get-Content`.

## Documentation

- [Documentation index](docs/en/index.md)
- [Development guide](docs/en/development.md)
- [Compatibility notes](docs/en/gh-compatibility.md)

## Repository Selection

Commands operate on the current Git repository by default. You can also select a repository explicitly:

```bash
gc issue list -R owner/repo
gc pr list -R owner/repo
```

## Authentication

`gc` resolves tokens in this order:

1. `--token` option
2. `GC_TOKEN` environment variable
3. `~/.config/gc/config.json`, written by `gc auth login`

Useful commands:

```bash
gc auth login
gc auth status
gc auth token
gc auth logout
```

## License

MIT
