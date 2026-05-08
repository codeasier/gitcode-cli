# 兼容性说明

中文 | [English](../en/gh-compatibility.md)

`pygitcode` 目标是尽量让 `gh` 用户以熟悉的方式使用 GitCode CLI，同时适配 GitCode API 的实际行为。

## 已对齐能力

| 能力 | `gc` 支持情况 |
| --- | --- |
| Issue 和 PR 的 list/view/create/comment/edit/close 流程 | 支持 |
| 根据当前分支推断 PR 编号 | 支持 |
| `pr create --fill`、`--fill-first`、`--fill-verbose` | 支持 |
| 适用命令中的 `--editor`、`--dry-run`、`--web` | 支持 |
| `--json`、`-q`、`-t` 输出处理 | 支持 |
| `ls` → `list`、`new` → `create` 等命令别名 | 支持 |
| 重复传入 `--label` 等多值参数 | 支持 |
| `--add-label` / `--remove-label` 等编辑辅助参数 | 支持 |

## GitCode 差异与限制

| 范围 | `gc` 中的差异 |
| --- | --- |
| 认证方式 | GitCode 使用 `access_token` 查询参数，不同于 GitHub API 的认证模型。 |
| Issue 创建/更新 API | GitCode 创建/更新 issue 时会在请求体中传入 `repo`，而不是只依赖 URL 路径。 |
| PR 行内评论 | GitCode 使用 `path + position` 模型；GitHub 的 `line`、`side`、`commit` 坐标不能直接等价映射。 |
| PR review request changes | `gc pr review --request-changes` 会近似为 PR 评论，因为 GitCode review API 与 GitHub 不同。 |
| Issue 删除 | `gc issue delete` 依赖 GitCode issue 删除行为，该接口目前未在公开 API 中明确记录，后续可能变化。 |
| Draft/ready 操作 | `gc pr ready --undo` 通过 GitCode 的 PR 更新能力切换 draft 状态，但语义可能不同于 GitHub draft PR。 |
| 浏览器流程 | `--web` 会打开对应 GitCode 页面；页面内创建或编辑能力取决于 GitCode Web UI。 |
