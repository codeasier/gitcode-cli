# 兼容性说明

中文 | [English](../en/gh-compatibility.md)

`pygitcode` 目标是尽量让 `gh` 用户以熟悉的方式使用 GitCode CLI，同时适配 GitCode API 的实际行为。

## 可选 gh 代理

`gc setup gh-proxy` 会在独立的用户目录中安装由 `gc` 管理的 `gh` shim，不会注册或覆盖 Python 包安装目录中的 `gh` console script。推荐同时配置检测到的 shell 和 OpenCode：

```bash
gc setup gh-proxy --configure
```

`--configure` 会在检测到的 zsh、bash、fish 或 PowerShell profile 中写入带标记且幂等的 `PATH` 配置块；同时创建 `gh-proxy-instructions.md` 并注册到全局 OpenCode `instructions` 数组，要求 agent 在 WebFetch、curl 或手写 API 前先验证并使用 `gh`。OpenCode 不会热加载指令，配置后必须重启。在 PowerShell 中请使用 `gitcode setup gh-proxy --configure` 避免与内置 `gc` 别名冲突。只运行 `gc setup gh-proxy` 仍保持仅安装模式，便于希望手动配置的用户使用。

路由优先级如下：

1. `GC_GH_TARGET=gitcode|github`
2. 显式 `-R HOST/OWNER/REPO` 或 `--repo` 参数中的 host
3. `repo view/clone/fork/edit/delete/sync` 的仓库位置参数中的 host（忽略选项值）
4. 当前仓库 `origin` 的 host
5. 无法判断目标时使用原生 GitHub CLI

默认识别 `gitcode.com` 和 `ssh.gitcode.com`，包括 `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`。`ssh://git@ssh.github.com:443/OWNER/REPO.git` 等 GitHub SSH 地址会路由到原生 `gh`。私有部署可以通过 `GC_GITCODE_HOSTS` 配置逗号分隔的额外 host。自动查找原生 `gh` 失败时，可用 `GC_REAL_GH` 指定其可执行文件。代理查找时会排除自身目录；在 POSIX 上通过进程替换保留原始参数、标准流、信号和退出状态。

GitCode 路由采用失败关闭策略：兼容性注册表中不存在的命令会直接拒绝，不会转发给 GitHub。`gc setup gh-proxy --uninstall` 会移除 shim，并且只删除由该命令管理且带标记的 shell/OpenCode 配置。

在 GitCode 仓库中，`gh --version` 会明确标识 pygitcode proxy、GitCode 目标和 `gc` 后端；`gh auth status` 会显示 `gitcode.com`、GitCode API host、脱敏 token，并明确提示命令目标是 GitCode 而非 GitHub。在 GitHub 仓库中，这两个命令仍保持原生 GitHub CLI 输出。

## 已对齐能力

| 能力 | `gc` 支持情况 |
| --- | --- |
| Issue 和 PR 的 list/view/create/comment/edit/close 流程 | 支持 |
| 仓库的 view/list/create/clone/fork/edit/rename/delete/sync 流程 | 支持 |
| 根据当前分支推断 PR 编号 | 支持 |
| `pr create --fill`、`--fill-first`、`--fill-verbose` | 支持 |
| 适用命令中的 `--editor`、`--dry-run`、`--web` | 支持 |
| `--json`、`-q`、`-t` 输出处理 | 支持 |
| `ls` → `list`、`new` → `create` 等命令别名 | 支持 |
| 重复传入 `--label` 等多值参数 | 支持 |
| `--add-label` / `--remove-label` 等编辑辅助参数 | 支持 |
| `auth status --json hosts`、`--jq`、`--template` | 支持；格式化选项需要配合 `--json` |
| `pr reopen --comment`、`pr diff --name-only` | 支持 |
| `pr checkout --detach`、`--force` | 支持，使用已配置的 `origin` |
| `pr comment --edit-last`、`--create-if-none`、`--delete-last`、`--yes` | 支持，限当前用户的普通 PR 评论 |
| `pr diff --patch` | 支持，返回按提交划分的邮件格式补丁 |

### 结构化认证状态

`gc auth status --json hosts` 通过 GitCode API 验证当前用户，返回以 `gitcode.com` 为键的 `hosts` 映射。输出始终不包含 token；无法获取的 scopes 与 Git 协议字段省略。缺少 token 时返回 `{"hosts": {}}`；API 或网络认证验证失败时返回 `state: "error"` 的条目，退出码仍为 0。配置损坏、JSON 字段错误、jq 表达式错误或格式化参数错误仍会失败。gh proxy 启用时也保持纯机器可读输出。

```bash
gc auth status --json hosts
gc auth status --json hosts --jq '.hosts["gitcode.com"][0].login'
gc pr diff 42 --name-only
gc pr reopen 42 --comment "Ready for another review"
gc pr checkout 42 --detach
gc pr checkout 42 --force
```

`--template` 复用 CLI 已有的 Go template 子集。`pr diff --name-only` 通过单次请求读取完整文件变更集合，包含二进制、重命名和删除的文件。[文件变更端点](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-files/)未声明分页参数。`pr reopen --comment` 先重开 PR 再发表评论；评论失败时命令以失败退出，并明确报告 PR 已重开。

PR checkout 要求源分支位于 `origin`。`--detach` 检出刚拉取的 head，不创建或重置本地分支。`--force` 只重置跟踪对应 `origin` 分支的已有本地分支，会丢弃该分支的本地提交与受跟踪文件的工作区修改；已有无关分支仍会被拒绝。当 API 提供 head SHA 时，这两个参数会在改变本地检出状态前核对它与 `FETCH_HEAD` 是否一致。fork／源仓库不匹配或 API 查询到拉取之间 head 已更新时，会明确报错。

### PR 评论历史与补丁

```bash
gc pr comment 42 --edit-last --body "Updated review summary"
gc pr comment 42 --edit-last --create-if-none --body-file summary.md
gc pr comment 42 --delete-last --yes
gc pr diff 42 --patch > review.patch
```

评论历史操作读取全部分页，按创建时间选取当前用户最新的**普通 PR 评论**，不依赖更新时间或 API 返回顺序。身份判断优先使用稳定用户 ID，其次使用 login，始终不使用显示名称。行内评论与讨论回复不参与选择。身份、评论类型、分页或创建时间无法确认时，命令在写入前失败。`--create-if-none` 必须配合 `--edit-last`，且仅在完整、有效的历史中不存在匹配评论时创建。`--yes` 必须配合 `--delete-last`；否则删除前会确认，默认选择否。

历史参数不能与行内评论、讨论回复或 web 参数混用。编辑支持 `--body`、`--body-file`（`-` 表示标准输入）与 `--editor`，编辑器预填选中评论的正文。未显式指定正文来源时，交互模式打开编辑器，非交互模式要求提供正文来源。取消编辑或正文为空时不写入。

评论修改与删除使用 GitCode 官方文档中的[编辑](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-comments-id)和[删除](https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-comments-id)接口。`--patch` 使用 `GET /repos/{owner}/{repo}/pulls/{number}/patch`，已于 2026-10-30 对公开仓库 `GitCode-official-team/GitCode-Docs` 的 PR #1 做只读探测，确认返回邮件格式补丁。该端点未列入公开 v5 文档；CLI 拒绝非补丁响应，不会用聚合 diff 替代。`--patch` 与 `--name-only` 互斥。请将 `--patch` 输出重定向到文件或管道：返回文本以 UTF-8 字节写出，不剥除 ANSI 序列、不转换或追加换行。直接输出到终端会在写出任何补丁字节前被拒绝，避免执行不可信终端控制序列；普通 `pr diff` 仍用于可读查看。

## GitCode 差异与限制

| 范围 | `gc` 中的差异 |
| --- | --- |
| 认证方式 | GitCode 使用 `access_token` 查询参数，不同于 GitHub API 的认证模型。 |
| Issue 创建/更新 API | GitCode 创建/更新 issue 时会在请求体中传入 `repo`，而不是只依赖 URL 路径。 |
| PR 行内评论 | GitCode 使用 `path + position` 模型，`position` 为文件绝对行号。`--line` 校验行号位于 PR diff 中后原样传递；`--position` 跳过 diff 校验。`--side` 仅选择校验侧，不会发送给 GitCode，因此 LEFT 侧锚定仅为尽力支持，不保证准确。不支持选择 commit。 |
| PR review request changes | `gc pr review --request-changes` 会近似为 PR 评论，因为 GitCode review API 与 GitHub 不同。 |
| Issue 删除 | `gc issue delete` 依赖 GitCode issue 删除行为，该接口目前未在公开 API 中明确记录，后续可能变化。 |
| Draft/ready 操作 | `gc pr ready --undo` 通过 GitCode 的 PR 更新能力切换 draft 状态，但语义可能不同于 GitHub draft PR。 |
| 仓库同步 | `gc repo sync` 仅支持通过 GitCode fork 同步 API 从上游同步 fork；不支持分支选择与 `--force`。 |
| 仓库归档 | 未实现 `gc repo archive`/`unarchive`；GitCode 仅文档化了一个缺少请求参数说明的 org 级归档端点。 |
| 仓库主题与部署密钥 | GitCode v5 没有仓库 topics 和 deploy-key API，`repo edit --add-topic/--remove-topic` 与 `repo deploy-key` 不可用。 |
| 浏览器流程 | `--web` 会打开对应 GitCode 页面；页面内创建或编辑能力取决于 GitCode Web UI。 |
