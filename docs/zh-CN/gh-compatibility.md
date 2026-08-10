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
3. 当前仓库 `origin` 的 host
4. 无法判断目标时使用原生 GitHub CLI

默认识别 `gitcode.com` 和 `ssh.gitcode.com`，包括 `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`。`ssh://git@ssh.github.com:443/OWNER/REPO.git` 等 GitHub SSH 地址会路由到原生 `gh`。私有部署可以通过 `GC_GITCODE_HOSTS` 配置逗号分隔的额外 host。自动查找原生 `gh` 失败时，可用 `GC_REAL_GH` 指定其可执行文件。代理查找时会排除自身目录；在 POSIX 上通过进程替换保留原始参数、标准流、信号和退出状态。

GitCode 路由采用失败关闭策略：兼容性注册表中不存在的命令会直接拒绝，不会转发给 GitHub。`gc setup gh-proxy --uninstall` 会移除 shim，并且只删除由该命令管理且带标记的 shell/OpenCode 配置。

在 GitCode 仓库中，`gh --version` 会明确标识 pygitcode proxy、GitCode 目标和 `gc` 后端；`gh auth status` 会显示 `gitcode.com`、GitCode API host、脱敏 token，并明确提示命令目标是 GitCode 而非 GitHub。在 GitHub 仓库中，这两个命令仍保持原生 GitHub CLI 输出。

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
