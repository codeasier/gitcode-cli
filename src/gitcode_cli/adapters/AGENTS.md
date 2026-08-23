# AGENTS.md — `adapters/` (gh-semantics translation layer)

Parent scope: the `gitcode_cli` package ([../AGENTS.md](../AGENTS.md)). Build/test commands are documented at the repository root.

## What this directory owns

Translation between what a `gh` user asked for and what the GitCode API can actually do. Adapters call `services/` exclusively; they never build HTTP requests themselves and never print output. Commands in `../commands/` call adapters and branch on the returned `AdapterActionResult`.

| File | Role |
|---|---|
| `base.py` | `AdapterActionResult` dataclass — the layer's return protocol (below). |
| `capabilities.py` | `CAPABILITY_MESSAGES` — every user-visible "GitCode cannot do X" message, keyed by constants like `ISSUE_LIST_APP` or `PR_EDIT_BASE`, plus `unsupported(key)` which builds the `ClickException`. |
| `issues.py` | `IssueAdapter(service, user_service=None)` — list (with pagination and client-side multi-label AND filtering), create (label existence check, milestone title→number resolution), close/reopen (idempotency checks against current state), comment history (edit/delete last own comment), edit (label/assignee merge logic), status (approximation), develop (browser no-op). |
| `pulls.py` | `PullRequestAdapter(service)` — list (pagination + `--limit` normalization), create (incl. `--dry-run` payload echo), merge, review (see degradation below), edit, status (approximation). |

## The `AdapterActionResult` protocol

`item` / `items` (payload), `message` (result classification), `warning`, and the flags `degraded` / `approximated`. Commands consume the classification strings literally, so treat them as an API:

- `manage_comment_history` returns `"deleted"` / `"created"` / `"edited"` — `commands/issue.py` branches on `"deleted"` and `"created"`.
- `close_issue` returns `"already_closed"` / `"already_closed_commented"` / `"closed"`; `reopen_issue` returns `"already_open"` / `"reopened"`.
- `degraded=True` from `review_pr` makes `gc pr review --request-changes` **fail** with the capability message after posting a plain PR comment (GitCode has no request-changes review) — the comment is still posted, then `commands/pr.py` raises.
- `approximated=True` (`issue status`, `pr status`) means output prints with a semantics caveat; adapters must carry the matching `CAPABILITY_MESSAGES` text, not ad-hoc strings.

## Capability keys and the registry

Adding an unsupported behavior requires three coordinated additions: the `unsupported("<KEY>")` guard in `../commands/`, the `KEY` in `CAPABILITY_MESSAGES` here, and a registry row with that `unsupported_key` in `../compat/entries.py`. `tests/unit/compat/test_registry_consistency.py` enforces all three exist together; see [../compat/AGENTS.md](../compat/AGENTS.md).

## Conventions worth preserving

- **Pagination lives here, not in services.** Loops fetch `per_page=100` (or `min(limit, 100)` for issue lists) until a short page or the requested limit is reached. `_normalize_limit` in `pulls.py` defines the `--limit` semantics commands rely on: `None` → default 30, negative → fetch everything at 100/page, `0` → empty result, positive → capped page size with exact truncation.
- **`@me` resolution** (`issues.py`) needs `user_service`; adapters that receive `None` must raise a `ClickException` explaining the lookup is unavailable rather than silently skipping the filter.
- **Client-side filtering** is the escape hatch for API gaps: multi-label AND semantics (GitCode's `labels` param is OR), assignee removal, and label merge on edit all re-read current state via `service.get(...)` and compute the full replacement payload.
- Ownership checks (`_find_last_owned_comment`) compare the current user's login against comment authors; when the login cannot be established they raise the `ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE` capability error instead of guessing — keep that refusal behavior.

## Tests

`tests/unit/adapters/` tests each adapter against mock services; `tests/unit/commands/test_issue_adapter_boundary.py` and `test_pr_adapter_boundary.py` pin the command→adapter delegation surface (argument names and adapter calls), so renaming an adapter method parameter ripples into those files.
