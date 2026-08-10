# Using This Project With an Agent

## What You Can Ask an Agent To Do

You can ask an agent to help you:

- install `pygitcode` from PyPI
- install this repository from source in editable mode
- authenticate with GitCode using `gc auth login`, `GC_TOKEN`, or `--token`
- run common issue and pull request commands
- troubleshoot token, repository selection, and command invocation problems
- review upgrade notes before you update to a newer release

## What To Tell the Agent First

Before the agent starts, tell it:

- your OS and shell
- whether you want to use the published package or this cloned repository
- whether it may install packages, edit local config files, run networked commands, or open a browser
- whether it must avoid printing or exposing tokens
- whether you are on Windows PowerShell, where `gitcode` is safer than `gc`
- whether you want to work against the current Git repository or an explicit `OWNER/REPO`

## Recommended Prompt Templates

### Install / First Setup

```text
Please help me install pygitcode on this machine. First read README.md and docs/en/USING_WITH_AGENT.md, then check whether Python 3.9+ and pip are available. Use the published install path unless the repository checkout is the better fit. Before any action that installs packages or writes auth config, tell me what you plan to do.
```

### Start Using It

```text
Please help me start using this GitCode CLI. First read README.md and docs/en/USING_WITH_AGENT.md, then verify whether I should use gc or gitcode in this shell. Help me authenticate safely, confirm which repository context will be used, and walk through one issue command and one pull request command.
```

### Upgrade / Update

```text
Please help me upgrade pygitcode safely. First read CHANGELOG.md, README.md, and docs/en/USING_WITH_AGENT.md. Do not perform destructive actions. Show me the current installed version, propose the upgrade path, then upgrade and verify the CLI still works.
```

### Troubleshooting

```text
Please troubleshoot why pygitcode is not working for me. First read README.md, docs/en/USING_WITH_AGENT.md, and CHANGELOG.md, then check installation, Python version, whether gc or gitcode should be used in this shell, token setup, repository detection, and the exact failing command.
```

## What the Agent Should Read First

Ask the agent to read these files first:

- `README.md`
- `docs/en/USING_WITH_AGENT.md`
- `CHANGELOG.md`
- `docs/en/index.md`
- `docs/en/gh-compatibility.md`
- `docs/en/development.md` when you are installing from source instead of PyPI

## Installation / Setup Flow

For published installation, the repository documents this command:

```bash
pip install pygitcode
```

This installs both `gc` and `gitcode` commands.

### Optional transparent gh routing

If an agent defaults to `gh`, you can install the optional managed proxy:

```bash
gc setup gh-proxy
export PATH="$(gc setup gh-proxy --print-path):$PATH"
```

The agent should verify that `gh --version` still reaches the native GitHub CLI outside a GitCode repository, then run a safe read-only command in each repository type. The proxy chooses `GC_GH_TARGET` first, then an explicit repository host, then the current `origin`; unknown contexts use native `gh`. It refuses unsupported commands for a confirmed GitCode target. Use `GC_REAL_GH` when native discovery fails and `gc setup gh-proxy --uninstall` to remove the shim.

For source installation, the repository documents this setup flow:

```bash
git clone https://github.com/codeasier/gitcode-cli.git
cd gitcode-cli
pip install -e ".[dev]"
```

The agent should usually:

1. verify Python and pip availability
2. confirm whether you want PyPI install or source install
3. install the package
4. verify whether `gc` or `gitcode` should be used in your shell
5. help configure authentication
6. run a minimal verification command such as `gitcode version` or `gc version`

## Authentication Flow

This project resolves tokens in this order:

1. `--token`
2. `GC_TOKEN`
3. `~/.config/gc/config.json`

The documented auth commands are:

```bash
gc auth login
gc auth status
gc auth token
gc auth logout
```

The agent should ask before:

- writing `~/.config/gc/config.json`
- printing a token to the terminal
- storing a token anywhere outside the documented config path

If you prefer non-interactive auth, tell the agent whether it may use `GC_TOKEN` or `gc auth login --with-token`.

## First Run / Basic Usage

The README documents these basic commands:

```bash
gc issue list
gc issue view 42
gc pr list
gc pr create --fill
gc pr merge 42 --squash
```

It also documents explicit repository selection:

```bash
gc issue list -R owner/repo
gc pr list -R owner/repo
```

The agent should help you:

1. confirm authentication is available
2. confirm whether the current directory is a Git repository
3. decide whether to rely on the current repository or use `-R owner/repo`
4. run one safe read-only command first, such as `gc issue list` or `gc pr list`
5. only then move on to create, comment, merge, or review actions if you ask for them

## Update / Upgrade Flow

This repository provides a `CHANGELOG.md` and follows semantic versioning. Before upgrading, the agent should:

1. read `CHANGELOG.md`
2. identify your current installed version with `gc version` or `gitcode version`
3. check whether you installed from PyPI or from source
4. propose the exact upgrade command based on that install method
5. verify authentication and one basic CLI command after the upgrade

If you use the repository checkout directly, ask the agent to read `docs/en/development.md` before changing the editable install.

## Troubleshooting Flow

If installation or usage fails, the agent should check, in order:

1. Python version requirement (`>=3.9`)
2. whether `pygitcode` is installed
3. whether this shell should use `gc` or `gitcode`
4. whether authentication is present via `--token`, `GC_TOKEN`, or `~/.config/gc/config.json`
5. whether the current directory is a Git repository with a usable `origin` remote
6. whether the command should use `-R owner/repo` instead of auto-detection
7. whether the failing command is a recognized but not yet implemented `gh`-compatible feature

Useful facts from the repository:

- `gc` mirrors familiar `gh` command shapes, but some compatibility gaps still exist
- on Windows PowerShell, `gitcode` is preferred because `gc` conflicts with `Get-Content`
- some commands intentionally reject unsupported `gh` flags rather than silently guessing behavior

## Actions Requiring Confirmation

An agent should ask before it:

- installs or upgrades packages
- writes authentication config
- prints or exports tokens
- opens browser-based authentication or web URLs
- creates, edits, closes, merges, reopens, or comments on issues or pull requests
- deletes a remote branch during `pr merge --delete-branch`
- runs commands against a repository other than the current one

## Notes

- The published package name is `pygitcode`.
- The CLI exposes both `gc` and `gitcode`.
- `gc auth login` prompts for a token unless you use `--with-token`.
- If current repository detection is unreliable, tell the agent to prefer `-R owner/repo`.
- For unsupported or partially compatible `gh` behavior, ask the agent to read `docs/en/gh-compatibility.md` first.
