# Current-account aliases

The standalone value `@me` resolves through `GET /user` to the authenticated account's **login**, never its display name or a guessed `username`, for:

- `gc pr list --author @me` and `--assignee @me`;
- `gc issue list --author @me` and `--assignee @me`;
- `gc issue create --assignee @me`;
- `gc issue edit --add-assignee @me` and `--remove-assignee @me`.

Multiple aliases in one operation share one current-user lookup. Ordinary login values are passed through unchanged and do not trigger a lookup. This does not add repeated/comma-separated Issue assignee options or change the existing Issue assignment semantics. PR create/edit people operations retain their separate [role-aware behavior](pr-people.md).

An unavailable lookup, failed request, missing login, display-name-only response, or malformed login stops the operation before the Issue/PR request. The CLI does not send literal `@me`, silently remove a filter, retry a mutation, or substitute a display name. A PR list with `--limit 0` remains a no-request operation.

Unit regressions and strict `.invalid` HTTP contracts cover lookup ordering, serialized filter/assignment values, ordinary logins, zero-limit lists and failure-before-write behavior using only synthetic credentials. They are offline coverage, not live permission acceptance. Required CLI CI must pass; a separately authorized sandbox can verify that the selected account matches the token's actual owner.
