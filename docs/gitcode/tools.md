# GitCode MCP tools

Use the live tool schemas as the authority for optional fields. All tools are namespaced with `gitcode_`, use explicit `owner` and `repo` arguments, and enforce the server's repository allowlist. Issue tools use `issue_number`; PR tools use `pull_number`.

The complete catalog has **31 tools: 19 reads and 12 writes**. Read-only mode, or an OAuth grant without `gitcode:write`, exposes only the 19 read tools.

In OAuth mode, each tool call uses the GitCode authorization belonging to that MCP connection. It cannot fall back to a shared PAT. The configured repository allowlist still applies, and reads require the grant's `gitcode:read` scope.

## Repository reads

| Tool | Result |
| --- | --- |
| `gitcode_get_repository` | Repository metadata and access check |
| `gitcode_get_clone_info` | Credential-free HTTPS/SSH clone URLs and default branch; no checkout |
| `gitcode_list_branches` | Branches |
| `gitcode_get_branch` | One branch |
| `gitcode_get_file_contents` | A file or directory at a ref |
| `gitcode_get_repository_tree` | Repository tree |
| `gitcode_list_commits` | Commits |
| `gitcode_get_commit` | One commit |

## Issue reads

| Tool | Result |
| --- | --- |
| `gitcode_list_issues` | Repository issues |
| `gitcode_get_issue` | One issue |
| `gitcode_list_issue_comments` | Issue comments |
| `gitcode_list_labels` | Available repository labels |
| `gitcode_list_milestones` | Repository milestones |

## Pull-request reads

| Tool | Result |
| --- | --- |
| `gitcode_list_pull_requests` | Repository PRs |
| `gitcode_get_pull_request` | One PR |
| `gitcode_list_pull_request_files` | Changed files |
| `gitcode_get_pull_request_diff` | PR diff |
| `gitcode_list_pull_request_comments` | PR comments |
| `gitcode_list_pull_request_commits` | PR commits |

## Write operations

These operations require server write mode, sufficient GitCode permissions, and the applicable client/user authorization. OAuth connections also require `gitcode:write`. Enabling server write mode or refreshing tool schemas does not expand an existing read-only grant: reconnect or repeat OAuth authorization for the extra scope. Writes are not implied by a read-only investigation.

| Tool | Effect |
| --- | --- |
| `gitcode_create_branch` | Create a remote branch |
| `gitcode_create_file` | Create one file and commit it to an explicit remote branch |
| `gitcode_update_file` | Replace one file and commit it, supplying the current file Blob SHA |
| `gitcode_delete_file` | Delete one file and commit it, supplying the current file Blob SHA |
| `gitcode_create_issue` | Create an issue |
| `gitcode_update_issue` | Update an issue |
| `gitcode_add_issue_comment` | Add an issue comment |
| `gitcode_create_pull_request` | Create a PR from existing remote branches |
| `gitcode_update_pull_request` | Update a PR |
| `gitcode_add_pull_request_comment` | Add a PR comment |
| `gitcode_approve_pull_request` | Approve a PR |
| `gitcode_merge_pull_request` | Merge a PR |

### File publishing parameters and results

All three file tools require `owner`, `repo`, `path`, `branch` and `message`. The branch must already exist; use `gitcode_create_branch` when starting a work branch. Create and update also require `content`, with `encoding: "utf-8"` by default or `"base64"` for explicitly encoded data. Update replaces the entire file. Update and delete require `sha`, the current file's 40-character hexadecimal **Blob SHA**, not the branch's commit SHA.

Decoded file content is limited to **256 KiB (262,144 bytes)**. Commit messages are limited to **4,096 UTF-8 bytes**. MCP HTTP requests are limited to **2 MiB** to accommodate JSON escaping; OAuth forms retain their separate 16 KiB limit. The server encodes content for GitCode and sends one Contents API write per tool call. Each write is a separate commit. The tools do not provide a multi-file transaction, branch-head compare-and-swap, force update or automatic rollback. Do not parallelize writes to the same branch.

The result's `data` identifies the operation, explicit branch and path, and reports `status: "accepted"`. It contains `commit_sha` and `content_sha` only when supplied by the upstream response; either can be `null`. When the commit SHA is absent, `verification_required` is `true`: read the target branch and file state to verify the change. A later branch HEAD is an observation, not proof that it is the commit created by this call. Do not repeat a write merely to obtain a missing SHA. Errors marked `operation_may_have_completed: true` also require remote inspection before any retry. See [code publishing](code-publishing.md) for the complete workflow and handling partial completion.

## Pagination and results

Paginated tools take `page` starting at 1 and `per_page` up to 100, with a default of 30. Results include `data` and pagination fields. A full page can produce a conservative `next_page` even if the following page is empty; stop on an empty page or when no next page is returned.

Some upstream lists lack documented server pagination. For those tools, `pagination_mode: "client"` means the server fetched one bounded response and returned a local slice, with `total_items` and `next_page`. Each page request fetches current upstream state again; it is not a stable snapshot. If a response exceeds the configured size limit, use a narrower query where supported or inspect the diff in the actual Git checkout.

The server returns structured data and a text representation for clients that consume text results. It does not return authentication tokens. Inspect returned IDs and remote state before retrying writes after a network failure, because the upstream operation may already have completed.

## GitCode-specific behavior

- Issue updates require `title`; read and preserve the current title when changing only another field. Update actions use `state: "close"` or `"reopen"`, while issue list filters use `"open"`, `"closed"`, or `"all"`.
- A cross-repository PR uses `head: "username:branch"` and `fork_path: "owner/repo"`. Both source and target repositories must be allowed when a server allowlist is configured. PR `assignees` means reviewers; `testers` is a separate GitCode role.
- Approval uses GitCode's native review endpoint with `force: false`. Add review text using the separate PR comment tool. The server does not emulate GitHub's `REQUEST_CHANGES` event with a normal comment.
- Merge accepts `merge_method: "merge"` or `"rebase"`, with `squash` as a separate boolean. It does not bypass permissions or branch protection and does not promise an atomic expected-head check that the upstream API does not document.
- The tree tool follows upstream pagination and retains available metadata. Missing upstream truncation information is reported as unknown, not as proof of completeness.
- The diff tool returns `format: "gitcode_structured_diff"` from GitCode's documented `files.json` endpoint, including native diff references and content. It does not manufacture a unified diff from incomplete data.

The PR update API documents `state` as a string without an enum. This release uses the existing `pygitcode` close/reopen mapping (`"closed"` / `"open"`); account-level acceptance still needs the optional live checks. API contract tests use fixtures and do not establish a live deployment.

## Deliberate execution boundary

The file tools publish changes through GitCode's API using the connection's authorization. They do not execute a shell, mount a workspace, create a checkout, run project tests or export tokens. Use the actual coding environment for native clone, fetch, pull, commit and push, and for running checks. `gitcode_get_clone_info` returns URLs only. `gitcode_create_branch` creates a GitCode branch; it does not create or switch a branch in any local working tree.
