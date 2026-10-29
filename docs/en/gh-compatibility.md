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
2. the host in an explicit `-R HOST/OWNER/REPO` or `--repo` value
3. the Issue/PR URL's host, or the repository positional's host for `repo view/clone/fork/edit/delete/sync` (option values are ignored)
4. the current repository's `origin` host
5. the native GitHub CLI when the target cannot be determined

`gitcode.com` and `ssh.gitcode.com` are recognized by default, including `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`. GitHub SSH endpoints such as `ssh://git@ssh.github.com:443/OWNER/REPO.git` route to the native `gh`. Set `GC_GITCODE_HOSTS` to a comma-separated list of additional GitCode deployment hosts. Set `GC_REAL_GH` to the native `gh` executable if automatic discovery cannot find it. The proxy excludes its own directory while searching, preserving arguments, standard streams, signals, and exit status on POSIX through process replacement.

GitCode routing fails closed: commands absent from the compatibility registry are rejected rather than sent to GitHub. `gc setup gh-proxy --uninstall` removes the shim and only the marked shell/OpenCode configuration managed by this command.

An Issue/PR URL conflicting with an explicit host or `GC_GH_TARGET` is rejected. Direct `gc` Issue/PR commands validate the effective URL, `-R`, or origin host before accessing the API; foreign hosts are never mapped to a same-named GitCode repository. A complete GitCode URL works outside a local checkout. `GC_GITCODE_HOSTS` changes proxy selection only; it does not change the CLI's fixed GitCode API endpoint or authorize foreign hosts.

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

## GitCode differences and limitations

| Area | Difference in `gc` |
| --- | --- |
| Authentication | GitCode uses an `access_token` query parameter rather than GitHub's API authentication model. |
| Issue create/update API | GitCode issue create/update sends `repo` in the request body. Updates also require `title`; close/reopen and partial edits preserve the fetched title and refuse to write if it is unavailable. |
| PR squash | `--squash` sends `merge_method=merge` and the separate boolean `squash=true`, following the current GitCode contract. |
| PR checkout and branch deletion | Require a fully qualified source repository identity and full head SHA. Fetch uses the source repository's canonical HTTPS URL and verifies the fetched commit. Deletion uses an explicit SHA lease so concurrent pushes are preserved. Missing/contradictory source metadata is rejected; a bare repository name or `head.ref` alone is insufficient. Native Git HTTPS credentials must be available. |
| Write outcomes | A merge must explicitly report `merged=true` (or integer `1`) before success or branch deletion. Redirects, accepted-but-pending responses, malformed JSON and unexpected empty responses are errors. If the outcome is uncertain, verify the remote state before retrying. A completed merge/close followed by refused branch deletion exits nonzero and reports that partial result. |
| PR inline comments | GitCode uses `path + position`, where `position` is an absolute file line. `--line` validates against the PR diff and passes the line through; `--position` bypasses diff validation. `--side` only selects the validation side and is not sent to GitCode, so LEFT anchoring is best-effort. Selecting a commit is unsupported. |
| PR review changes | `gc pr review --request-changes` is approximated with a PR comment because GitCode's review API differs from GitHub's. |
| Issue deletion | `gc issue delete` relies on GitCode issue deletion behavior that is not documented in the public API and may change. |
| Draft/readiness operations | `gc pr ready --undo` toggles draft state through the GitCode PR update capability; behavior may differ from GitHub draft PR semantics. |
| Repository sync | `gc repo sync` only syncs a fork from its upstream via the GitCode fork sync API; branch selection and `--force` are not available. |
| Repository archive | `gc repo archive`/`unarchive` are not implemented; GitCode documents only an org-scoped archive endpoint without request parameters. |
| Repository topics and deploy keys | GitCode v5 has no repository topics or deploy-key API, so `repo edit --add-topic/--remove-topic` and `repo deploy-key` are unavailable. |
| Browser flows | `--web` opens the corresponding GitCode page; browser-created content depends on GitCode's web UI. |

On POSIX, saved token configuration uses a private directory (`0700`), atomic file replacement (`0600`), and rejects linked storage. HTTP transport logs and raised errors redact the active token. Windows file privacy relies on the user's profile ACL.

The squash/title contracts were checked against the [merge](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge) and [Issue update](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number) documentation on 2026-10-30. Offline contract checks do not establish live sandbox compatibility.
