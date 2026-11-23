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

Only repository discussions are targeted, by positive discussion number. Supply `-R` on the root or the subcommand, or use a GitCode checkout. Create/edit require the existing category **name**, title and Markdown body (`-b`, `-F file`, or `-F -` for stdin). The update endpoint requires all three values: a partial edit is rejected instead of silently overwriting fields from an earlier read. Comment reads the target discussion ID once, then adds one top-level comment. The CLI checks the returned fields and identities before reporting success. Writes are never retried; if a write's result is uncertain, inspect the discussion before deciding whether to repeat it.

List defaults to open discussions, newest update first. GitCode supports server-side search and creation-time ordering, not update-time ordering. For accurate update-time sorting, gc reads every page before applying the limit. Use `--sort created` to stop after enough matches. A repeated, malformed, or unexhausted 100th page yields an error rather than silently presenting an incomplete sort. Author login and category name filters use exact matches. `view --comments` shows top-level comments, newest first; it does not fetch nested replies.

This is a subset of the preview gh discussion surface, not GitHub GraphQL compatibility. Discussion/comment URLs, labels on writes, comment editing/deletion/replies, cursors, browser mode, and unlisted formatting flags are not supported. Use `--help` for available flags and JSON fields.

Official v5 definitions: [authenticated organizations](https://docs.gitcode.com/en/docs/orgs/), [list discussions](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss/), [view](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number/), [list comments](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-discuss-number-comment/), [create](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-discuss/), [edit](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-discuss-number/), and [add a comment](https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-discuss-number-comment/).

## List organization Kanban boards

`gc org dashboards --org acme` prints one page as board number (iid) and name. To select fields on the next page:

```sh
gc org dashboards --org acme --page 2 --per-page 20 --json id,iid,name,status,visibility
```

Use a single organization slug (an ASCII letter or digit, then letters, digits, dots, underscores or hyphens; at most 255 characters), not a URL, nested namespace or repository. No checkout is needed; `-R` is rejected. The CLI requests exactly one page (page 1–10000; 1–100 rows; default 20), not the full collection or its totals. Status is 0 (open) or 1 (closed); visibility is 1 (public) or 2 (private). The organization is the request scope: the API does not echo the parent organization on each board, so this command cannot verify row ownership independently. It does not infer any other fields, items, descriptions or permissions. A failed page produces no rows. This native, read-only command does not implement or forward `gh project`.

[GitCode's v5 list contract](https://docs.gitcode.com/docs/apis/get-api-v-5-org-owner-kanban-list/) defines the singular `org` route and envelope. [AtomGit endpoint 244](https://atomgit-api-doc.atomgit.com/en/16.dashboard/244.get_the_list_of_organization_kanbans.html) permits anonymous reads or a user access token, but names no required OAuth scope. An anonymous request explicitly filters for public boards (`visibility=1`) and rejects the entire page if any result is nonpublic or unrecognized. A configured token is sent only in the [GitCode Bearer header](https://docs.gitcode.com/en/docs/guide/); it may receive private boards if permitted by the provider. There is no auth fallback, redirect or automatic retry. The anonymous/authenticated access policy is documented and tested with mocked responses, not confirmed against a live GitCode organization.
