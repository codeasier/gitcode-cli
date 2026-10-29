# Publish code through GitCode MCP

The file tools let an authorized MCP connection publish code to a GitCode branch and then create a PR. They use the connection's GitCode API authorization; no SSH key, Git credential helper or additional PAT is needed in dot's shell for these calls.

## Contents

- [Choose the publishing route](#choose-the-publishing-route)
- [File tools and limits](#file-tools-and-limits)
- [Publish a change and open a PR](#publish-a-change-and-open-a-pr)
- [Verify results and handle failures](#verify-results-and-handle-failures)
- [OAuth permissions and upgrades](#oauth-permissions-and-upgrades)
- [Official API contracts](#official-api-contracts)

## Choose the publishing route

| Requirement | Route |
| --- | --- |
| Create, replace or delete individual files on a remote branch | Use the MCP file tools below |
| Publish several files with a separate commit for each | Call file tools sequentially on a work branch |
| Produce one commit containing multiple files, preserve a prepared local history, or use native Git features | Use Git in an actual coding environment with its own GitCode authentication |
| Run project tests, builds, formatters or other commands | Use an actual code execution environment |

The MCP server does not execute a shell, clone a repository, mount a workspace, run tests, return credentials or provide a force-ref operation. `gitcode_get_clone_info` returns credential-free URLs only. API publication does not require a native `git push`; the Contents API writes directly to GitCode.

## File tools and limits

| Tool | Effect | Additional required input |
| --- | --- | --- |
| `gitcode_create_file` | Create one new file and commit it | `content` |
| `gitcode_update_file` | Replace the full contents of an existing file and commit it | `content`, `sha` |
| `gitcode_delete_file` | Delete one existing file and commit it | `sha` |

All three require explicit `owner`, `repo`, `path`, `branch` and `message`. The target branch must exist. Use `gitcode_create_branch` to create a separate work branch before publication.

For create/update, `encoding` is `"utf-8"` by default: pass the complete text as `content`, and the server performs the Base64 encoding required by GitCode. Choose `"base64"` only when `content` is already encoded, including binary data. Decoded file content must be no larger than **256 KiB (262,144 bytes)**. A commit `message` must be no larger than **4,096 UTF-8 bytes**. These are byte limits, not character counts.

The MCP HTTP request limit is **2 MiB**, allowing room for JSON escaping as well as tool arguments. The Nginx example uses the same limit. OAuth form endpoints retain their separate **16 KiB** application limit. See [deployment upgrades](deployment.md#operate-and-upgrade) if an existing proxy still rejects larger requests.

For update/delete, `sha` must be the existing file's **40-character hexadecimal Blob SHA**, obtained from `gitcode_get_file_contents` for the target branch. It is not the branch's commit SHA. Do not use the SHA of the new content, a truncated SHA or an unrelated branch's version.

The Blob SHA is passed to GitCode's file API. It does not provide a whole-branch lock or an atomic expected-head check. Read the current content before preparing an update; if a conflict indicates the file changed, reconcile with that content instead of copying a new SHA onto a stale replacement.

## Publish a change and open a PR

1. **Read the target.** Resolve the repository and intended base branch using `gitcode_get_repository` and `gitcode_get_branch`. Read the Issue, applicable `AGENTS.md` instructions, relevant code and tests. Record the base commit; do not guess that every repository uses `main`.
2. **Create a work branch.** Call `gitcode_create_branch` with a scoped `branch_name` and `refs` set to the verified base commit. This creates a remote branch, not a local checkout.
3. **Read existing files on that branch.** Use `gitcode_get_file_contents` with `ref` set to the work branch. Preserve each file's Blob SHA for an update or deletion. For a new file, ensure the intended path does not already exist.
4. **Prepare and check the change.** Prepare complete replacement contents and review the intended diff. Run the project's relevant checks in an available coding environment. If checks cannot run, record that limitation explicitly; an MCP write does not run them or establish their result.
5. **Publish sequentially.** Call the appropriate file tool for each change, with the explicit work branch and a meaningful commit message. Record each result before moving to the next file. Do not parallelize writes to the same branch.
6. **Verify the remote result.** Inspect returned identifiers and re-read the branch and changed files as needed. Follow [verification guidance](#verify-results-and-handle-failures), especially when `verification_required` is `true`.
7. **Create the PR.** Call `gitcode_create_pull_request` using the verified work branch as `head` and the intended target as `base`. Describe the problem, changes, actual checks and limitations. Link the Issue where appropriate. Creating a PR does not imply approval to merge it.

For example, after creating `docs/example` from a verified base, a `gitcode_create_file` call can use:

```json
{
  "owner": "OWNER",
  "repo": "REPOSITORY",
  "path": "docs/example.md",
  "branch": "docs/example",
  "message": "docs: add usage example",
  "content": "# Usage example\n\nDescribe the supported behavior.\n",
  "encoding": "utf-8"
}
```

Replace `OWNER` and `REPOSITORY` with the actual target. To update an existing file, use `gitcode_update_file`, provide the full new content and add the current file's `sha` from the read on that branch. To delete it, use `gitcode_delete_file` with the same identifying fields and current `sha`, omitting `content` and `encoding`.

Each file call makes **one Contents API write and produces a separate commit**. Publishing three files means three commits, not one atomic multi-file commit. This tool surface does not expose an atomic batch operation or the GitHub-style blob/tree/commit/ref creation sequence.

## Verify results and handle failures

The result's `data` includes `operation`, `status: "accepted"`, `branch`, `path`, `commit_sha`, `content_sha` and `verification_required`, with a note when additional verification is needed. The response reports the write outcome without returning the full upstream payload or submitted file content.

`commit_sha` and `content_sha` contain only identifiers supplied by the upstream response. Either may be `null`; an accepted operation does not guarantee both identifiers are present. In particular, the documented update response can contain file metadata without a commit SHA.

When the commit SHA is absent, the result sets `verification_required: true`. Read the target branch and the affected path, compare the content and inspect relevant commit history if attribution matters. Treat a branch head observed later as current remote state; another writer may have advanced it since the file operation. Do not present that observation as an upstream-returned commit ID for the write, and do not repeat a successful write to try to obtain a SHA.

If a call fails, times out or returns an uncertain result:

- Stop publishing the remaining files and record the operations already confirmed.
- Re-read the work branch and affected path to determine whether the last write took effect. Distinguish an inaccessible path from a confirmed deletion.
- Do not automatically retry, recreate the branch or roll back earlier commits. A network error can occur after GitCode accepted the write.
- Reconcile concurrent edits before any intentional retry. Report partial completion and unresolved state accurately.

An error with `operation_may_have_completed: true` explicitly signals an uncertain write outcome. Inspect remote state before deciding what to do next; the flag is not a recommendation to retry. Its absence is not a general idempotency guarantee for future calls.

There is no multi-file transaction: earlier file commits remain when a later operation fails. Use a scoped work branch so partial publication can be inspected before creating or updating a PR.

## OAuth permissions and upgrades

Writes require `GITCODE_MCP_READ_ONLY=false`, the connection's `gitcode:write` scope, the server's repository allowlist and sufficient upstream GitCode permissions. Branch protections still apply. OAuth credentials remain on the MCP host; the model does not need to receive them for file publication.

For an existing cloud deployment moving from `codex-codeasier`, follow [migration and rollback](migration.md) to preserve its URL, clients, configuration and OAuth state. For later updates, pin the checkout, rebuild/reinstall and recreate/restart the runtime, then refresh the plugin's tools in ChatGPT. Preserve the OAuth database and encryption key. The full catalog has **31 tools: 19 reads and 12 writes**; read-only connections still expose 19.

An existing write grant covers these file tools without new authorization solely for the upgrade. A read-only grant must be authorized again to obtain `gitcode:write`; refreshing its access token or the tool list does not broaden its scopes. Changes to the upstream GitCode application's permissions, an expired grant or revoked authorization may independently require reconnection. See [deployment](deployment.md#operate-and-upgrade) and [OAuth configuration](oauth.md).

## Official API contracts

The implementation follows GitCode's documented Contents endpoints:

- [Create a file: POST contents](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-contents-path/)
- [Update a file: PUT contents](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-contents-path/)
- [Delete a file: DELETE contents](https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-contents-path/)
- [Read file contents and the current Blob SHA](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contents-path/)
- [GitCode API authentication](https://docs.gitcode.com/docs/apis/)

The public contracts do not establish an atomic multi-file commit or a branch-head compare-and-swap operation for these endpoints. The service does not add undocumented `actions`, `last_commit_id`, `force` or GitHub Git Data fields to make such a claim.
