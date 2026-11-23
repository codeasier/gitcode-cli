# Compatibility notes

[中文](../zh-CN/gh-compatibility.md) | English

`pygitcode` aims to feel familiar to `gh` users while adapting to GitCode API behavior.

## Optional gh proxy

`gc setup gh-proxy` installs a managed `gh` shim in an isolated user directory; it does not register or overwrite a `gh` package console script. The recommended setup also configures the detected shell and OpenCode:

```bash
gc setup gh-proxy --configure
```

`--configure` writes a marked, idempotent `PATH` block to the detected zsh, bash, fish, or PowerShell profile. It also creates `gh-proxy-instructions.md`, registers it in the global OpenCode `instructions` array, and tells agents to verify and use `gh` before WebFetch, curl, or handwritten API requests. Restart OpenCode after configuration because it does not hot-reload instructions. Use `gitcode setup gh-proxy --configure` on PowerShell to avoid its built-in `gc` alias. Plain `gc setup gh-proxy` remains install-only for users who prefer manual configuration.

Routing priority is:

1. `GC_GH_TARGET=gitcode|github`
2. the host in explicit `-R HOST/OWNER/REPO` / `--repo`, or a native host selector on `gh api` / `gh auth`
3. the Issue/PR URL's host, or the repository positional's host for `repo view/clone/fork/edit/delete/sync` (option values are ignored)
4. the current repository's `origin` host
5. the native GitHub CLI when the target cannot be determined

`gitcode.com` and `ssh.gitcode.com` are recognized by default, including `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`. GitHub SSH endpoints such as `ssh://git@ssh.github.com:443/OWNER/REPO.git` route to the native `gh`. Set `GC_GITCODE_HOSTS` to a comma-separated list of additional GitCode deployment hosts. Set `GC_REAL_GH` to the native `gh` executable if automatic discovery cannot find it. The proxy excludes its own directory while searching, preserving arguments, standard streams, signals, and exit status on POSIX through process replacement.

GitCode routing fails closed: commands and flags known to be unsupported are rejected without calling either backend. Commands marked direct-only, such as `gc api` and `gc pr checks`, are never forwarded by the proxy. For recognized issue and PR selectors, a GitCode URL still selects this policy outside a GitCode checkout. `gc setup gh-proxy --uninstall` removes the shim and only the marked shell/OpenCode configuration managed by this command.

Conflicting explicit GitCode and GitHub targets are rejected before either backend runs. This includes a repository positional, Issue/PR URL, `--repo`, `--hostname` and `GC_GH_TARGET`. A native `--hostname` can select the GitHub backend, but does not become a supported flag on the GitCode backend. Direct `gc` Issue/PR commands validate the effective URL, `-R`, or origin host before accessing the API; foreign hosts are never mapped to a same-named GitCode repository. A complete GitCode URL works outside a local checkout, including repository URLs with one optional trailing slash. The proxy does not translate native `GH_HOST` or `GH_REPO` into GitCode arguments. If either names a recognized GitCode host, an explicit compatible GitCode argument is required; otherwise use `gc` directly. Native GitHub values are left unchanged. `GC_GITCODE_HOSTS` changes proxy selection only; it does not change the CLI's fixed GitCode API endpoint or authorize foreign hosts.

In a GitCode repository, `gh --version` identifies itself as the pygitcode proxy and names the GitCode target and `gc` backend. `gh auth status` similarly reports `gitcode.com`, the GitCode API host, a masked token, and an explicit notice that commands target GitCode rather than GitHub. In a GitHub repository, both commands continue to use the native GitHub CLI output.

## Aligned capabilities

| Capability | Status in `gc` |
| --- | --- |
| Issue and PR list/view/create/comment/edit/close flows | Supported |
| Repository view/list/create/clone/fork/edit/rename/delete/sync flows | Supported |
| PR identifier inference from the current branch | Supported |
| `pr create --fill`, `--fill-first`, `--fill-verbose` | Supported |
| `--editor`, `--dry-run`, and `--web` where applicable | Supported |
| `--json`, `-q`, and `-t` output shaping | Supported |
| Command aliases such as `ls` → `list`, `new` → `create` | Supported |
| Multi-value options such as repeated `--label` | Supported |
| Edit helpers such as `--add-label` / `--remove-label` | Supported |
| `auth status --json hosts`, `--jq`, and `--template` | Supported; formatting options require `--json` |
| `pr reopen --comment` and `pr diff --name-only` | Supported |
| `pr checkout --detach` and `--force` | Supported using the verified PR source |
| `pr comment --edit-last`, `--create-if-none`, `--delete-last`, and `--yes` | Supported for the current user's ordinary PR comments |
| `pr diff --patch` | Supported; returns per-commit mail-format patches |

### Local accounts and structured authentication status

`gc auth status --json hosts` verifies the listed accounts through the GitCode API and returns a `hosts` map for `gitcode.com`. Use `--active` to verify only the effective account. See [local GitCode accounts](auth-accounts.md) for PAT login and switching. Tokens are never included in this output. Unavailable scopes and Git protocol are omitted. A missing token returns `{"hosts": {}}`; an API or network authentication failure returns an entry with `state: "error"` and exit code 0. Invalid configuration, JSON fields, jq expressions, or formatting options still fail. JSON output stays machine-readable when the gh proxy is active.

```bash
gc auth status --json hosts
gc auth status --json hosts --jq '.hosts["gitcode.com"][0].login'
gc pr diff 42 --name-only
gc pr reopen 42 --comment "Ready for another review"
gc pr checkout 42 --detach
gc pr checkout 42 --force
```

`--template` uses the CLI's existing Go-template subset. `pr diff --name-only` reads the complete changed-files collection in one request, including binary, renamed, and deleted files. The [changed-files endpoint](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-files/) has no documented pagination parameters. `pr reopen --comment` posts the comment after reopening; if commenting fails, the command exits unsuccessfully and reports that the PR was already reopened.

PR checkout fetches from the verified source repository rather than assuming `origin` contains the source branch. `--detach` checks out the verified immutable head SHA without creating or resetting a local branch. `--force` resets an existing branch only when its upstream identifies that source repository and branch, discarding its local commits and tracked working-tree changes. Missing, unrelated or ambiguous upstreams are refused; remote names need not be `origin`. Without `--force`, an existing branch must already point to the verified SHA. New branches are created at that SHA. If exactly one existing remote has the canonical HTTPS/SSH source URL and standard branch fetch mapping, its upstream is retained; a missing tracking ref is created with a compare-and-swap guard, never overwriting an existing ref. Otherwise no upstream is invented: configure an unambiguous source remote/upstream before using `--force` later. Custom ports, embedded HTTPS credentials and remote helpers are not accepted as proof of upstream identity. No temporary routing remote is saved. All modes require a full API head SHA and reject a head changed between the API read and fetch before changing the local checkout. URL pinning addresses Git configuration rewrites; it does not disable native HTTPS redirects or replace Git authentication.

### PR comment history and patches

```bash
gc pr comment 42 --edit-last --body "Updated review summary"
gc pr comment 42 --edit-last --create-if-none --body-file summary.md
gc pr comment 42 --delete-last --yes
gc pr diff 42 --patch > review.patch
```

Comment history reads every page and selects the current user's newest **ordinary PR comment** by creation time, not update time or API response order. Stable user IDs take precedence over logins; display names are never used to establish ownership. Inline comments and discussion replies are excluded. If identity, comment type, pagination, or creation time cannot be established, the command fails before writing. `--create-if-none` requires `--edit-last` and creates only when a complete, valid history has no matching comment. `--yes` requires `--delete-last`; otherwise deletion prompts for confirmation with a default of no.

History flags cannot be combined with inline-comment, discussion, or web options. Editing accepts `--body`, `--body-file` (including `-` for stdin), or `--editor`; the editor starts with the selected comment's text. Without an explicit body source, interactive editing opens the editor; non-interactive use requires a body source. Cancelling the editor or submitting an empty body does not write anything.

Comment updates and deletion use GitCode's documented [edit](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-comments-id) and [delete](https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-comments-id) endpoints. `--patch` uses `GET /repos/{owner}/{repo}/pulls/{number}/patch`, observed to return a mail-format patch in a read-only probe against public `GitCode-official-team/GitCode-Docs` PR #1 on 2026-10-30. This patch endpoint is not listed in the public v5 reference; the CLI rejects non-patch responses and does not substitute an aggregate diff. `--patch` and `--name-only` are mutually exclusive. Redirect or pipe `--patch` output: it writes the returned text as UTF-8 bytes without stripping ANSI sequences, translating newlines, or adding a newline. Direct terminal output is rejected before writing any patch bytes so untrusted terminal control sequences cannot execute; ordinary `pr diff` remains the human-readable view.

## GitCode differences and limitations

| Area | Difference in `gc` |
| --- | --- |
| Authentication | GitCode uses an `access_token` query parameter rather than GitHub's API authentication model. |
| Issue create/update API | GitCode issue create/update sends `repo` in the request body. Updates also require `title`; close/reopen and partial edits preserve the fetched title and refuse to write if it is unavailable. |
| PR status | Use `gc pr status -R OWNER/REPO -c` (`--conflict-status`) for the first page of open PRs, up to 20. It reads each [PR detail](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/) once and reports only GitCode’s `mergeable_state.conflict_passed` check: passed, not passed, or unknown when absent/non-boolean. This is not merge readiness. A failed detail request or inconsistent identity aborts the report; without `-c` no detail requests are made. The GitCode-targeted proxy refuses `gh pr status`: this repository view does not implement [gh’s personal status](https://cli.github.com/manual/gh_pr_status), current-branch group, or JSON contract. For scriptable authored PRs, use `gc pr list -s open -A @me --json number,title`. |
| PR squash | `--squash` sends `merge_method=merge` and the separate boolean `squash=true`, following the current GitCode contract. |
| PR checkout and branch deletion | Require a fully qualified source repository identity and full head SHA. Fetch uses the source repository's canonical HTTPS URL and verifies the fetched commit. Deletion uses an explicit SHA lease so concurrent pushes are preserved. Missing/contradictory source metadata is rejected; a bare repository name or `head.ref` alone is insufficient. Native Git HTTPS credentials must be available. URL rewrites that change the effective fetch/push URL are refused; accepted operations pin a command-scoped target without changing saved Git configuration. |
| Write outcomes | A merge must explicitly report `merged=true` (or integer `1`) before success or branch deletion. Redirects, accepted-but-pending responses, malformed JSON and unexpected empty responses are errors. If the outcome is uncertain, verify the remote state before retrying. A completed merge/close followed by refused branch deletion exits nonzero and reports that partial result. |
| PR inline comments | GitCode uses `path + position`, where `position` is an absolute file line. `--line` validates against the PR diff and passes the line through; `--position` bypasses diff validation. `--side` only selects the validation side and is not sent to GitCode, so LEFT anchoring is best-effort. Selecting a commit is unsupported. |
| PR review changes | `--approve` uses [native approval](https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-review/). Unlike older gc versions, `--request-changes` exits nonzero **without posting**: no equivalent blocking review action was verified. Use `--comment` only if ordinary feedback is intended. |
| PR merge guards | The [merge request schema](https://docs.gitcode.com/en/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge/) does not document an expected head or per-PR auto-merge enable/disable. The returned SHA is not an input precondition. `--match-head-commit`, `--auto` and `--disable-auto` refuse; no read-then-unconditional merge or polling fallback. |
| PR update/revert/lock | The [PR API index](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/) does not establish update-branch, revert-to-new-PR or conversation lock/unlock operations. A read-only locked flag or a web UI action does not verify a write contract. |
| Issue links, moderation and transfer | `gc issue develop N --list` [reads linked names](https://atomgit-api-doc.atomgit.com/3.issues/73.get_the_list_of_branches_associated_with_the_issue.html). The [branch setter](https://docs.gitcode.com/en/docs/apis/put-api-v-5-repos-owner-repo-issues-number-related-branches/) accepts a list, not an atomic create-and-append. The [Issue API index/update schema](https://docs.gitcode.com/en/docs/apis/patch-api-v-5-repos-owner-issues-number/) does not establish lock/unlock, pin/unpin, or transfer. No branch-list replacement, close-and-copy or label emulation is attempted. |
| Issue deletion | `gc issue delete` relies on GitCode issue deletion behavior that is not documented in the public API and may change. |
| Draft/readiness operations | `gc pr ready --undo` toggles draft state through the GitCode PR update capability; behavior may differ from GitHub draft PR semantics. |
| Repository sync | `gc repo sync [-b BRANCH]` syncs one remote fork branch from its parent, never all branches. See [fork sync](repo-sync.md); arbitrary `--source`, `--force` and local sync are not supported. |
| Repository archive | `gc repo view --json isArchived` reads the [repository status](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/) and reports `null` if the state is unknown or contradictory. GitCode documents an [organization-scoped status update](https://docs.gitcode.com/docs/apis/put-api-v-5-org-org-repo-repo-status/): integer `2` archives and `0` restores. Neither write is implemented in gc. |
| Repository topics and deploy keys | GitCode v5 has no repository topics or deploy-key API, so `repo edit --add-topic/--remove-topic` and `repo deploy-key` are unavailable. |
| Browser flows | `--web` opens the corresponding GitCode page; browser-created content depends on GitCode's web UI. |

On POSIX, saved token configuration uses a private directory (`0700`), atomic file replacement (`0600`), and rejects linked storage. HTTP transport logs and raised errors redact the active token. Windows file privacy relies on the user's profile ACL.

The squash/title contracts were checked against the [merge](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge) and [Issue update](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number) documentation on 2026-10-30. Offline contract checks do not establish live sandbox compatibility.
