# Organizations and repository discussions

`gc org list` (alias `ls`) prints the authenticated user's organization logins, one per line. The default limit is 30; raise it with `-L`. It works outside a checkout.

```sh
gc org list -L 50
gc discussion ls -R OWNER/REPO --search "build" --state open --json number,title
gc discussion view 8 -R OWNER/REPO --comments --limit 10
gc discussion create -R OWNER/REPO -c General -t "Roadmap" -F roadmap.md
gc discussion edit 8 -R OWNER/REPO -c General -t "Updated roadmap" -F roadmap.md
gc discussion comment 8 -R OWNER/REPO -b "Which release is this targeting?"
```

Only repository discussions are targeted, by positive discussion number. Supply `-R` on the root or the subcommand, or use a GitCode checkout. Create/edit require the existing category **name**, title and Markdown body (`-b`, `-F file`, or `-F -` for stdin). The update endpoint requires all three values: a partial edit is rejected instead of silently overwriting fields from an earlier read. Comment adds one top-level comment. Writes are never retried; if a write's result is uncertain, inspect the discussion before deciding whether to repeat it.

List defaults to open discussions, newest update first. GitCode supports server-side search and creation-time ordering, not update-time ordering. For accurate update-time sorting, gc reads every page before applying the limit. Use `--sort created` to stop after enough matches. A repeated, malformed, or unexhausted 100th page yields an error rather than silently presenting an incomplete sort. Author login and category name filters use exact matches. `view --comments` shows top-level comments, newest first; it does not fetch nested replies.

This is a subset of the preview gh discussion surface, not GitHub GraphQL compatibility. Discussion/comment URLs, labels on writes, comment editing/deletion/replies, cursors, browser mode, and unlisted formatting flags are not supported. Use `--help` for available flags and JSON fields.

Official v5 definitions: [authenticated organizations](https://docs.gitcode.com/en/docs/orgs/), [list discussions](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss/), [view](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number/), [list comments](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment/), [create](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-discuss/), [edit](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-discuss-number/), and [add a comment](https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-discuss-number-comment/).
