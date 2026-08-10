# Compatibility notes

[中文](../zh-CN/gh-compatibility.md) | English

`pygitcode` aims to feel familiar to `gh` users while adapting to GitCode API behavior.

## Optional gh proxy

`gc setup gh-proxy` installs a managed `gh` shim in an isolated user directory; it does not register or overwrite a `gh` package console script. Add the printed directory before the native GitHub CLI directory in `PATH`:

```bash
gc setup gh-proxy
export PATH="$(gc setup gh-proxy --print-path):$PATH"
```

On PowerShell, use `gitcode` to avoid the built-in `gc` alias and prepend the directory with `$env:Path = "$(gitcode setup gh-proxy --print-path);$env:Path"`.

Routing priority is:

1. `GC_GH_TARGET=gitcode|github`
2. the host in an explicit `-R HOST/OWNER/REPO` or `--repo` value
3. the current repository's `origin` host
4. the native GitHub CLI when the target cannot be determined

`gitcode.com` and `ssh.gitcode.com` are recognized by default, including `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`. Set `GC_GITCODE_HOSTS` to a comma-separated list of additional GitCode deployment hosts. Set `GC_REAL_GH` to the native `gh` executable if automatic discovery cannot find it. The proxy excludes its own directory while searching, preserving arguments, standard streams, signals, and exit status on POSIX through process replacement.

GitCode routing fails closed: commands absent from the compatibility registry are rejected rather than sent to GitHub. Remove the managed shim with `gc setup gh-proxy --uninstall`.

## Aligned capabilities

| Capability | Status in `gc` |
| --- | --- |
| Issue and PR list/view/create/comment/edit/close flows | Supported |
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
| Issue create/update API | GitCode issue create/update sends `repo` in the request body instead of encoding it only in the URL path. |
| PR inline comments | GitCode uses `path + position`; GitHub-style `line`, `side`, and `commit` review coordinates are not equivalent. |
| PR review changes | `gc pr review --request-changes` is approximated with a PR comment because GitCode's review API differs from GitHub's. |
| Issue deletion | `gc issue delete` relies on GitCode issue deletion behavior that is not documented in the public API and may change. |
| Draft/readiness operations | `gc pr ready --undo` toggles draft state through the GitCode PR update capability; behavior may differ from GitHub draft PR semantics. |
| Browser flows | `--web` opens the corresponding GitCode page; browser-created content depends on GitCode's web UI. |
