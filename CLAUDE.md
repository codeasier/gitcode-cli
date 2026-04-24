# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`gc` is a Python CLI tool for GitCode (api.gitcode.com), modeled after GitHub's `gh` CLI. It provides terminal-based management of Issues and Pull Requests via the GitCode REST API v5.

## Commands

```bash
# Install (editable mode, exposes `gc` command)
pip install -e .

# Run directly
python -m gitcode_cli

# No tests directory exists yet; tests/ is empty
# No linter/formatter config exists yet
```

## Architecture

```
src/gitcode_cli/
├── cli.py          # Click entry point: top-level group, --repo/-R, --token, version
├── client.py       # GitCodeClient: httpx-based HTTP wrapper, auto-injects access_token
├── config.py       # Token resolution: CLI arg > GC_TOKEN env > ~/.config/gc/config.json
├── context.py      # AppContext dataclass: holds token + repo, produces client()
├── errors.py       # Exception hierarchy: GCError → ConfigError, AuthError, RepoResolutionError, APIError
├── repo.py         # resolve_repo(): -R flag or git remote origin → (owner, repo) tuple
├── formatters.py   # Output helpers (currently just dump_json)
├── commands/       # Click subcommand groups
│   ├── auth.py     # gc auth login
│   ├── issue.py    # gc issue list/view/create/close/comment
│   └── pr.py       # gc pr list/view/create/close/merge/comment/review
└── services/       # Thin GitCode API wrappers
    ├── issues.py   # IssueService: CRUD + comments
    └── pulls.py    # PullRequestService: CRUD + merge + comments + review
```

**Request flow**: `commands/*.py` → resolves repo via `repo.resolve_repo()` → instantiates service with `AppContext.client()` → service calls `GitCodeClient` which hits `https://api.gitcode.com/api/v5/`.

## Key Design Decisions

- **src-layout** with `pip install -e .` exposing the `gc` console script.
- **Token priority**: `--token` flag > `GC_TOKEN` env var > config file (`~/.config/gc/config.json`).
- **Repo resolution**: explicit `-R OWNER/REPO` or auto-detect from `git remote get-url origin` (supports HTTPS and SSH URLs).
- **Issue create/update** uses `/repos/:owner/issues` with `repo` in the request body (not in the URL path like PRs).
- **PR comment** uses GitCode's `path + position` model (not GitHub's `line/side/commit`).
- **PR review** currently only supports `--approve`; GitCode's review API differs from `gh`.
- Most list commands support `--json` for machine-readable output; default is human-readable tabular/text.

## GitCode API Notes

- Base URL: `https://api.gitcode.com/api/v5/`
- Auth: `access_token` query parameter on every request
- Issue paths: `/repos/:owner/:repo/issues`, `/repos/:owner/issues` (create/update includes `repo` in body)
- PR paths: `/repos/:owner/:repo/pulls`, `/repos/:owner/:repo/pulls/:number/merge`, etc.