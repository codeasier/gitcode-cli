# Compatibility notes

[中文](../zh-CN/gh-compatibility.md) | English

`pygitcode` aims to feel familiar to `gh` users while adapting to GitCode API behavior.

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
