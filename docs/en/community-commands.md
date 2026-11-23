# Organizations and repository discussions

`gc org list` (alias `ls`) prints the authenticated user's organization logins, one per line. The default limit is 30; raise it with `-L`. It works outside a checkout.

```sh
gc org list -L 50
gc discussion ls -R OWNER/REPO --search "build" --state open --json number,title
gc discussion view 8 -R OWNER/REPO --comments --limit 10
gc discussion view 8 -R OWNER/REPO --comments --json comments
gc discussion replies 8 COMMENT_ID -R OWNER/REPO --page 1 --per-page 20 --json id,author,body
gc discussion create -R OWNER/REPO -c General -t "Roadmap" -F roadmap.md
gc discussion edit 8 -R OWNER/REPO -c General -t "Updated roadmap" -F roadmap.md
gc discussion comment 8 -R OWNER/REPO -b "Which release is this targeting?"
```

Only repository discussions are targeted, by positive discussion number. Supply `-R` on the root or the subcommand, or use a GitCode checkout. Create/edit require the existing category **name**, title and Markdown body (`-b`, `-F file`, or `-F -` for stdin). The update endpoint requires all three values: a partial edit is rejected instead of silently overwriting fields from an earlier read. Comment reads the target discussion ID once, then adds one top-level comment. The CLI checks the returned fields and identities before reporting success. Writes are never retried; if a write's result is uncertain, inspect the discussion before deciding whether to repeat it.

List defaults to open discussions, newest update first. GitCode supports server-side search and creation-time ordering, not update-time ordering. For accurate update-time sorting, gc reads every page before applying the limit. Use `--sort created` to stop after enough matches. A repeated, malformed, or unexhausted 100th page yields an error rather than silently presenting an incomplete sort. Author login and category name filters use exact matches. `view --comments` shows top-level comments, newest first; it does not fetch nested replies.

Use `view --comments --json comments` to obtain the `id` of a top-level comment. `discussion replies NUMBER COMMENT_ID` reads exactly one page for that comment in the given repository discussion. It makes one read-only [v5 replies request](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment-comment-id-reply/), preserves the server's order, and does not traverse other comments or replies. `--page` starts at 1; `--per-page` defaults to 20 and accepts 1–100. Pages are not an immutable snapshot. The documented response does not echo the parent ID. Even on a nonempty page, the association comes from the requested URL, not independent confirmation in the rows. An empty page (`[]` in JSON) does not distinguish a missing parent from a page with no replies. JSON fields are `id`, `author` (login), `body` (Markdown), `createdAt`, `hidden`, and `deleted`. Hidden/deleted replies show status; their selected author and body fields are `null`. JSON escapes control and non-ASCII characters without changing the decoded Markdown.

This is a subset of the preview gh discussion surface, not GitHub GraphQL compatibility or a gh proxy mapping. Discussion/comment URLs, labels on writes, editing/deleting comments, posting replies, cursors, browser mode, and unlisted formatting flags are not supported. Use `--help` for available flags and JSON fields.

Official v5 definitions: [authenticated organizations](https://docs.gitcode.com/en/docs/orgs/), [list discussions](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss/), [view](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number/), [list comments](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment/), [create](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-discuss/), [edit](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-discuss-number/), and [add a comment](https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-discuss-number-comment/).
