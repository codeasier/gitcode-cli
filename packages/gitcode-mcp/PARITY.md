# GitCode MCP parity

Baselines: [GitHub MCP Server v2.3.0](https://github.com/github/github-mcp-server/blob/v2.3.0/README.md#tools), [GitCode CLI v0.2.0](https://github.com/codeasier/gitcode-cli/releases/tag/v0.2.0), and the GitCode MCP 0.3.0 registry. Compare workflows, not names or numbers of tools. GitHub's hosted and optional toolsets are not all enabled in a default installation.

| Workflow | GitCode MCP status | Follow-up / limit |
| --- | --- | --- |
| Read repositories, branches, files, commits and trees; create branches | Covered | Repository allowlist and bounded responses apply. A normalized directory page and explicit fork sync status remain separate candidates. |
| Create, update or delete a single file | Covered | Not a multi-file commit. A prior blob SHA is not a branch HEAD precondition. |
| Publish a multi-file commit | Platform contract unverified | Do not simulate with sequential single-file writes. A native Git alternative requires proven delegated write authentication and authenticated actor, one commit and one ref update, expected old HEAD, server-enforced non-force update, branch protection, and readback. The local clone helper is not a push transport. |
| Repository creation and fork; repository deletion | CLI available, MCP gap | Use dedicated tools and validate target and authorization. Deletion should not share the same tool as ordinary repository modification. |
| Read and write Issues, comment, and read labels | Covered in part | Child Issues, custom fields, notification handling and team operations need separate platform evidence. |
| Manage repository task-label definitions | Candidate in this batch | Not Issue label assignment. Read-only grants must neither list nor invoke mutation tools. Check the existing label identity before update or delete; a separate read does not provide atomic compare-and-swap. |
| Open, edit, comment on, approve and merge PRs | Covered in part | Existing approve/merge is not a guarantee that the reviewed HEAD was atomically pinned by the platform. |
| Inline PR comments and discussion replies | Candidate in this batch | One native write after verifying the target; no downgrade to a general comment. Feature is not a pending multi-comment review, thread resolution, or atomic HEAD lock. |
| Pending reviews, request changes, thread resolution, update PR branch | Contract check needed | Test individual server semantics before registering tools. Do not implement blind retries or fake a review state with text comments. |
| Workflow/run/job/PR-check reads; dispatch/stop/rerun/retry | CLI available in part; MCP OAuth contract unverified | CLI v0.2.0 uses a query token on the Actions client. Prove header-only delegated OAuth with restricted-repository GET plus an anonymous/denied control. Then verify each write on a separately approved disposable workflow. Do not fall back to query credentials or advertise full logs, retry semantics or server-atomic attempt locks without evidence. |
| Repository, user, Issue, PR and organization search | CLI available in part | A repo-only grant must not fan out across an account or organization and filter afterwards. Code/commit search require separate evidence. |
| Discussions, Release and Tag | Partial CLI backend, MCP gap | Separate supported read and write methods. Release writes and attachment transfer are GitCode opportunities, not a claim that the upstream GitHub MCP exposes release publishing. |
| GitHub Projects, governance, security alerts, Gists, Copilot | No direct parity claim | Validate true GitCode equivalents separately; an organization dashboard is not a Projects mutation API. |
| Local checkout, local file replacement, shell formatting, gh proxy | CLI only | Not remote MCP operations. Do not expose a generic subprocess or arbitrary API proxy. |

## Acceptance

Test through MCP `tools/list` and `tools/call` under stdio and HTTP OAuth. Verify repository allowlist rejection before upstream I/O, independent read/write grants, and fixed endpoint/method and redacted output. No secret or signed transfer data belongs in receipts.

For the review and label writes, use an authorized disposable repository. Observe the exact PR/HEAD/diff coordinates or label identity before calling, then verify the resulting comment, reply or label independently, including a refused stale or wrong-target operation. Offline contract tests are not a receipt for a live upstream OAuth write.

Update the CLI dependency and `published-cli.json` together only after obtaining and verifying the published wheel and sdist. Package publication, service deployment and client `tools/list` readback are separate checks.
