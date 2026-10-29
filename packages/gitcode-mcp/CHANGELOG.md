# MCP changelog

Versions and release tags in this file belong only to `codeasier-gitcode-mcp`.
A source entry is not evidence that the version has been published to PyPI.

## [0.3.0]

- Preserve the migrated 31-tool runtime (19 read, 12 write tools), OAuth state
  format, single-file code publishing, and clone helper from the recorded
  `codex-codeasier` baseline.
- Maintain independent Python 3.11+ packaging and the verified
  `pygitcode==0.1.6` runtime dependency.
- Add independent release validation and artifact publication preparation in
  `gitcode-cli`, including clean wheel/sdist installation, offline protocol and
  legacy-token checks, and real synthetic Compose-volume takeover/rollback CI.

No production deployment, downstream dependency switch, or publication is implied.
