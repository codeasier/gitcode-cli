# MCP changelog

Versions and release tags in this file belong only to `codeasier-gitcode-mcp`.
A source entry is not evidence that the version has been published to PyPI.

## [Unreleased]

## [0.4.0]

- Expand the catalog to 37 tools: 20 reads and 17 writes.
- Add a read-only fork synchronization status check.
- Fix browser consent across HTTPS origins without weakening Origin or CSRF
  checks. Reject ambiguous write responses and accept empty successful
  task-label deletions only after catalog readback.

- Add immediate PR inline comments and discussion replies, with target checks
  before one native write; neither is an atomic HEAD-bound review.
- Add repository task-label definition creation, update and deletion using
  the current authorization; existing Issue label assignment is unchanged.
- Record GitHub MCP parity, remaining upstream contracts, and acceptance gates.

## [0.3.0]

- Preserve the migrated 31-tool runtime (19 read, 12 write tools), OAuth state
  format, single-file code publishing, and clone helper from the recorded
  `codex-codeasier` baseline.
- Delegate existing repository and clone-metadata reads to the published
  `RepoService.get`, preserving MCP authorization, transport and result behavior.
- Pin the published `pygitcode==0.1.7` and delegate existing file tools to its
  `FileService`, preserving MCP validation, bearer transport and result semantics.
- Keep the immutable legacy migration seed and rollback on MCP `0.3.0` /
  `pygitcode==0.1.6`; candidate acceptance requires the new `0.1.7` runtime
  dependency.
- Maintain independent Python 3.11+ packaging and release validation in
  `gitcode-cli`, including clean wheel/sdist installation, offline protocol and
  legacy-token checks, real synthetic Compose-volume takeover/rollback CI, and
  a tag-only publication path with no long-lived PyPI token.

No production deployment, downstream dependency switch, or publication is implied.
