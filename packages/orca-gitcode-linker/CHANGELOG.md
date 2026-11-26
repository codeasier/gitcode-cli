# Orca GitCode Linker changelog

Versions and release tags in this file belong only to `orca-gitcode-linker`.
A source entry is not evidence that the version has been published.

## [Unreleased]

## [0.1.0]

- Expose GitCode pull requests through a local Gitea-compatible API that Orca's Gitea provider reads.
- Map GitCode REST v5 pull requests, merge state, branch metadata, and mergeability to Gitea rows.
- Resolve GitCode forks through `parentfull_name` so a fork worktree can see upstream merge requests.
- Read tokens from `gc` configuration, `GC_TOKEN`, or a token file without placing a real token in Orca's environment.
- Provide macOS LaunchAgent and Linux remote-runtime installers, with a localhost-only read-only adapter.
