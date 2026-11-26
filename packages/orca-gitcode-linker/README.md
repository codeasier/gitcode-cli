# Orca GitCode Linker

Orca's sidebar card reads pull-request state from hosted-review providers. It ships with
GitHub, GitLab, Bitbucket, Azure DevOps and Gitea providers, but no GitCode provider, so a
`gitcode.com` worktree is treated as a plain `git:` repository and shows no PR pill.

This distribution exposes the small Gitea API surface Orca reads and translates it to GitCode
REST v5. Orca keeps using its normal Gitea provider, while requests go to a local adapter
backed by the user's existing `gc` token.

```text
Orca sidebar card
  -> Gitea provider (ORCA_GITEA_API_BASE_URL)
    -> http://127.0.0.1:8765/api/v1
      -> https://api.gitcode.com/api/v5
```

The adapter is read-only and uses only the Python standard library.

## Install

From PyPI (after the package is published):

```bash
pipx install orca-gitcode-linker
```

From this checkout:

```bash
python -m pip install ./packages/orca-gitcode-linker
# or, for an isolated user install:
pipx install ./packages/orca-gitcode-linker
```

This installs the `orca-gitcode-linker` command. The macOS service installer prefers that
command when it is on `PATH`; otherwise it falls back to the package source tree. Service
installers are shipped in this repository and the sdist under `scripts/`; a wheel-only install
provides the server command, which you can run under your own service manager.

## Orca runtimes

Orca reads a local worktree through this machine's Orca process, but it reads a paired
environment's worktrees through that environment's `orcad` runtime. Install and configure the
adapter on every machine whose worktrees you want covered:

- local worktrees: this Mac's LaunchAgent and `ORCA_GITEA_*`;
- `linuxmint-ts`, `mac-mini-ts`, ...: an adapter plus `ORCA_GITEA_*` in the remote runtime's
  environment. A user `~/.pam_environment` is inherited by SSH-launched `orcad` on Linux; the
  remote systemd user service keeps the adapter running.
- SSH hosts that Orca drives from this Mac (not a paired environment) use this Mac's adapter.

For a Linux paired runtime, deploy the adapter and its systemd user service, then reconnect the
environment once so `orcad` inherits the new environment:

```bash
packages/orca-gitcode-linker/scripts/install_remote_linux.sh linuxmint-ts
```

The script uses port 8787 by default (`PORT=...` to override) because 8765 may already be taken.

## Requirements

- Orca desktop with the workspace-card review lane (the current card style).
- Python 3.9 or newer (`/usr/bin/python3` on macOS is sufficient).
- A GitCode token, normally from `gc auth login` (`~/.config/gc/config.json`). `GC_TOKEN` is
  also accepted.
- The repository's `origin` remote must point at the GitCode repository Orca knows. Orca passes
  that `owner/repo` to the adapter.
- On a GitCode fork, the adapter detects `parentfull_name` from the repository metadata and reads
  PRs from both the fork and its upstream parent by default. This is what makes worktrees whose
  `origin` is a personal fork see upstream merge requests.

## Install the macOS service

```bash
packages/orca-gitcode-linker/scripts/install_macos.sh
```

The installer:

- writes and starts a LaunchAgent (`com.codeasier.orca-gitcode-linker`);
- sets `ORCA_GITEA_API_BASE_URL=http://127.0.0.1:8765/api/v1`;
- sets a dummy `ORCA_GITEA_TOKEN` for Orca's integration status. The real GitCode token stays
  inside the adapter and is never placed in Orca's environment;
- installs `com.codeasier.orca-gitcode-env`, which re-applies those two `launchctl setenv`
  values at login (`launchctl setenv` itself does not survive a reboot).

If `orca-gitcode-linker` is installed in a pipx environment not on the installer's `PATH`, set
`ORCA_GITCODE_LINKER_BIN=/path/to/orca-gitcode-linker` before running the installer.

Quit and reopen Orca after installing: `launchctl setenv` only affects applications started
afterward. A window reload does not re-read the environment; check the process start time with
`ps -o lstart= -p $(pgrep -f '/Applications/Orca.app/Contents/MacOS/Orca' | head -1)` if in
doubt. Then open a GitCode worktree; the status lane should show its PR state.

To use another port, run `PORT=9000 packages/orca-gitcode-linker/scripts/install_macos.sh`.

## Manual run

```bash
orca-gitcode-linker --port 8765
# or without installing:
PYTHONPATH=packages/orca-gitcode-linker/src python3 -m orca_gitcode_linker --port 8765
```

Then launch Orca from that shell with:

```bash
export ORCA_GITEA_API_BASE_URL=http://127.0.0.1:8765/api/v1
export ORCA_GITEA_TOKEN=orca-gitcode-linker
open -a Orca
```

`GC_TOKEN`, `--token`, `--token-file`, and `~/.config/gc/config.json` are all supported token
sources. `orca-gitcode-linker --version` prints the distribution version.

## Verify

```bash
curl -fsS http://127.0.0.1:8765/api/v1/healthz
curl -fsS "http://127.0.0.1:8765/api/v1/repos/OWNER/REPO/pulls?state=open&page=1&limit=50"
```

Expected shapes:

- `GET /api/v1/repos/:owner/:repo/pulls?state=all|open|closed&page=N&limit=N` returns Gitea
  pull-request rows in newest-updated order. For a fork it may include upstream parent rows.
- `GET /api/v1/repos/:owner/:repo/pulls/:number` returns one row.
- `GET /api/v1/repos/:owner/:repo/commits/:sha/status` returns a neutral combined status.
- `GET /api/v1/version` and `GET /api/v1/user` satisfy Orca's Gitea auth-status probe.

Logs go to `~/Library/Logs/orca-gitcode-linker.log` for the LaunchAgent, or stderr in manual
mode. The adapter logs request paths and status codes, never the token.

## Limitations

- Read-only: it maps PR state, title, URL, head branch, mergeability and update time. Checks are
  reported as neutral because GitCode has no Gitea-compatible combined-status endpoint; PR
  creation, merge, review comments and file views are not implemented.
- `ORCA_GITEA_API_BASE_URL` is global to Orca's Gitea provider in one runtime. If you also use
  Codeberg or a self-hosted Gitea instance, its requests would be routed to this adapter too.
- Forks are resolved from GitCode's `parentfull_name`. Use `--fork-pr-source parent` to read
  only the upstream, or `origin` to disable fork lookup. A fork chain is followed at most three
  levels.
- Orca's Gitea branch scan reads at most five pages. On a busy upstream, PRs older than that
  window will not be found by branch name.
- Polling is cached for 15 seconds by default (`--cache-ttl`); repository parent metadata is
  cached for an hour.
- The adapter binds to `127.0.0.1` and intentionally has no local authentication; do not expose
  the port on a public interface.
- This relies on Orca's Gitea provider accepting unknown hosts. An Orca release could change
  that behavior; the long-term fix is a native `gitcode` provider upstream.

## Uninstall

```bash
packages/orca-gitcode-linker/scripts/install_macos.sh --uninstall
```

Then quit and reopen Orca.

## Independent release

`orca-gitcode-linker` is a third distribution in this repository, with its own Python version,
wheel/sdist, workflows and tag namespace. It does not depend on `pygitcode` or
`codeasier-gitcode-mcp`.

```bash
cd packages/orca-gitcode-linker
python -m pip install -e '.[dev]'
python -m ruff check --config pyproject.toml .
python -m ruff format --check --config pyproject.toml .
python -m pytest -c pyproject.toml tests
python -m build
```

Release preparation:

1. Add a non-empty `## [x.y.z]` section to this package's `CHANGELOG.md` and set the same
   version in `pyproject.toml`.
2. Tag `linker-vx.y.z`. The `Publish Orca GitCode Linker` workflow validates the tag, builds
   the wheel/sdist, and publishes with PyPI trusted publishing.
3. Before the first release, configure a **pending trusted publisher** on PyPI
   (Account -> Publishing -> Add a new pending publisher):

   | Field | Value |
   |---|---|
   | PyPI project name | `orca-gitcode-linker` |
   | Owner | `codeasier` |
   | Repository name | `gitcode-cli` |
   | Workflow name | `publish-orca-gitcode-linker.yml` |
   | Environment name | `pypi` |

   The `pypi` GitHub environment already exists, so no GitHub-side change is needed. The
   workflow uses OIDC and has no long-lived PyPI token. The pushed tag must point at a commit
   that contains the workflow file; a pending publisher becomes the project publisher after the
   first successful upload.
