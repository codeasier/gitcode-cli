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
2. 显式 `-R HOST/OWNER/REPO`、`--repo`，或原生 `gh api` / `gh auth` 的主机选择参数中的 host
3. Issue/PR URL 中的 host，或 `repo view/clone/fork/edit/delete/sync` 的仓库位置参数中的 host（忽略选项值）
4. 当前仓库 `origin` 的 host
5. 无法判断目标时使用原生 GitHub CLI

默认识别 `gitcode.com` 和 `ssh.gitcode.com`，包括 `ssh://git@ssh.gitcode.com:443/OWNER/REPO.git`。`ssh://git@ssh.github.com:443/OWNER/REPO.git` 等 GitHub SSH 地址会路由到原生 `gh`。私有部署可以通过 `GC_GITCODE_HOSTS` 配置逗号分隔的额外 host。自动查找原生 `gh` 失败时，可用 `GC_REAL_GH` 指定其可执行文件。代理查找时会排除自身目录；在 POSIX 上通过进程替换保留原始参数、标准流、信号和退出状态。

GitCode 路由采用失败关闭策略：已知不支持的命令和参数会直接拒绝，不会转发给任一后端。`gc api` 和 `gc pr checks` 等仅支持直接调用的命令不会由代理转发。对于可识别的 Issue 或 PR 参数，即使不在 GitCode 工作目录，GitCode 链接仍会选用这套路由规则。`gc setup gh-proxy --uninstall` 会移除 shim，并且只删除由该命令管理且带标记的 shell/OpenCode 配置。

显式的 GitCode 与 GitHub 目标互相冲突时，代理会在调用后端之前拒绝。检查范围包括仓库位置参数、Issue/PR URL、`--repo`、`--hostname` 和 `GC_GH_TARGET`。原生 `--hostname` 可以选用 GitHub 后端，但不会成为 GitCode 后端支持的参数。直接使用 `gc` 的 Issue/PR 命令会在访问 API 前校验有效 URL、`-R` 或 origin 的 host，不会将其他平台的目标映射为 GitCode 同名仓库。完整 GitCode URL 可在本地 checkout 之外使用，仓库 URL 可带一个末尾斜杠。代理不会把原生 `GH_HOST` 或 `GH_REPO` 转成 GitCode 参数。如果任一变量指向已识别的 GitCode 主机，须显式传入兼容的 GitCode 参数，否则请直接使用 `gc`。原生 GitHub 的变量值保持不变。`GC_GITCODE_HOSTS` 只改变代理路由，不会改变 CLI 固定的 GitCode API 地址，也不会授权其他 host。

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
| `pr checkout --detach`、`--force` | 支持，使用已验证的 PR 源仓库 |
| `pr comment --edit-last`、`--create-if-none`、`--delete-last`、`--yes` | 支持，限当前用户的普通 PR 评论 |
| `pr diff --patch` | 支持，返回按提交划分的邮件格式补丁 |

### 本地账号与结构化认证状态

`gc auth status --json hosts` 通过 GitCode API 验证列出的账号，返回以 `gitcode.com` 为键的 `hosts` 映射。`--active` 仅验证生效账号；PAT 登录与切换见[本地 GitCode 多账号](auth-accounts.md)。输出始终不包含 token；无法获取的 scopes 与 Git 协议字段省略。缺少 token 时返回 `{"hosts": {}}`；API 或网络认证验证失败时返回 `state: "error"` 的条目，退出码仍为 0。配置损坏、JSON 字段错误、jq 表达式错误或格式化参数错误仍会失败。gh proxy 启用时也保持纯机器可读输出。

```bash
gc auth status --json hosts
gc auth status --json hosts --jq '.hosts["gitcode.com"][0].login'
gc pr diff 42 --name-only
gc pr reopen 42 --comment "Ready for another review"
gc pr checkout 42 --detach
gc pr checkout 42 --force
```

`--template` 复用 CLI 已有的 Go template 子集。`pr diff --name-only` 通过单次请求读取完整文件变更集合，包含二进制、重命名和删除的文件。[文件变更端点](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-files/)未声明分页参数。`pr reopen --comment` 先重开 PR 再发表评论；评论失败时命令以失败退出，并明确报告 PR 已重开。

PR checkout 从已验证的源仓库拉取，不再假定源分支位于 `origin`。`--detach` 检出已核实的不可变 head SHA，不创建或重置本地分支。`--force` 只重置 upstream 对应同一源仓库及分支的已有本地分支，会丢弃该分支的本地提交与受跟踪文件的工作区修改。缺失、不相关或不明确的 upstream 均拒绝，remote 名称不必是 `origin`。不使用 `--force` 时，已有分支必须已指向核实的 SHA。新分支从该 SHA 创建；若现存 remote 中恰有一个使用规范 HTTPS/SSH 源 URL 及标准分支 fetch 映射，则保留对应 upstream。缺少 tracking ref 时，以 compare-and-swap 保护创建，绝不覆盖已有 ref。否则不擅自建立 upstream，之后使用 `--force` 前须明确配置源 remote/upstream。自定义端口、HTTPS URL 内嵌凭据和 remote helper 不作为 upstream 身份证明，不保存临时路由 remote。所有模式均要求 API 提供完整 head SHA；API 查询到拉取之间 head 已变化时，在改变本地检出状态前报错。URL 固定针对 Git 配置重写，不会禁用原生 HTTPS 重定向或替代 Git 认证。

### 按路径排除变更文件名

```bash
gc pr diff 42 --name-only --exclude '*.yml' -e 'generated/*'
```

直接调用 `gc` 会按原有顺序过滤文件列表，只匹配本来要显示的路径（重命名时不同时匹配新旧两个名字）。匹配完整路径或文件名，区分大小写，因此不含 `/` 的模式可以匹配任意层级的文件。`*` 可匹配单个路径分段内的零个或多个字符：`generated/*` 排除 `generated/a.py`，但保留 `generated/sub/a.py`。`**` 不递归。

每个选项只接受一个非空模式，最多重复指定 32 个模式，每个模式最多 512 个 UTF-8 字节。这是 [gh v2.105.0](https://github.com/cli/cli/blob/v2.105.0/pkg/cmd/pr/diff/diff.go) 的子集：查询前拒绝 `?`、方括号字符类、反斜杠转义、逗号、双引号和 不可打印字符。面向 GitCode 的 `gh` 代理不转发此选项。普通 diff 和邮件格式补丁正文不支持过滤。

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

## 设置检出目录的默认 GitCode 仓库

```sh
gc repo set-default upstream             # 已存在的 GitCode 远端名
gc repo set-default owner/repo            # 必须与唯一 GitCode 远端中的仓库名完全相同
gc repo set-default --view
gc repo set-default --unset
```

这是对 `gh repo set-default` 的**部分兼容，仅影响读取**。设置、查看或取消默认仓库只操作本地 Git 配置，链接的 worktree 共享该设置。无需认证或联网，不修改远端的获取/推送 URL 或原生 `gh` 配置。只能选择在该仓库本地配置中直接声明、且只有一个受支持 GitCode **fetch** URL 的远端；仅在 include 文件或其他配置作用域声明的远端不能固定。若有多个远端对应相同仓库，请指定远端名。不提供交互式选单或 fork 父仓库查询。

**只有直接调用 `gc repo view`、`gc repo read-file` 和 `gc repo read-dir` 时才使用此默认仓库。** 显式仓库参数或 `-R` 优先；显式空值报错。未设置时仍使用 origin。配置损坏、远端被删除或改指其他仓库、URL 有歧义或被重写时，命令会停止，不回退到 origin。可重新设置、取消设置或显式指定目标。

**刚查看的仓库不一定是后续写操作的目标。** Issue、PR（含创建、分支推断和 checkout）、Release、Actions、标签、讨论、原始 API 和所有仓库管理命令均不采用此设置，目标选择与原来相同。要写入刚查看的仓库，请在支持的命令上显式指定 `-R`。`gh` 代理不读取此设置，不转发目标为 GitCode 的 `repo set-default` 命令。

## GitCode 差异与限制

| 范围 | `gc` 中的差异 |
| --- | --- |
| 认证方式 | GitCode 使用 `access_token` 查询参数，不同于 GitHub API 的认证模型。 |
| Issue 创建/更新 API | GitCode 创建/更新 issue 时会在请求体中传入 `repo`。更新还要求 `title`；close/reopen 和部分字段编辑保留读取到的当前标题，无法取得标题时拒绝写入。 |
| PR 状态 | `gc pr status -R OWNER/REPO -c`（`--conflict-status`）查看仓库第一页的打开 PR，最多 20 个。它为每条记录读取一次 [PR 详情](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/)，只报告 `mergeable_state.conflict_passed`：通过、未通过，缺失或非布尔值显示未知；这不代表 PR 可以合入。详情读取失败或身份不一致时整个报告失败；不加 `-c` 不读取详情。仓库视图没有实现 [gh 个人状态](https://cli.github.com/manual/gh_pr_status)、当前分支分组及其 JSON 结构，指向 GitCode 的代理会拒绝 `gh pr status`。脚本可用 `gc pr list -s open -A @me --json number,title` 查询自己创建的打开 PR。 |
| PR squash | `--squash` 按当前 GitCode 契约发送 `merge_method=merge` 和独立布尔字段 `squash=true`。 |
| PR checkout 与分支删除 | 要求完整源仓库身份和完整 head SHA。fetch 使用源仓库规范 HTTPS URL 并校验提交；删除使用显式 SHA lease，保护并发推送。源元数据缺失或冲突时拒绝操作，仅仓库短名称或 `head.ref` 不足以定位。执行环境需具备原生 Git HTTPS 凭据。改变实际 fetch/push URL 的 Git 重写规则会被拒绝；通过核验的操作使用仅当前命令生效的固定目标，不修改持久 Git 配置。 |
| 写入结果 | merge 必须明确返回 `merged=true`（或整数 `1`）后才能报告成功或删除分支。重定向、已受理但未完成、非法 JSON 及非预期空响应均报错。结果不确定时应先核实远端状态再重试。已完成 merge/close 但分支删除被拒绝时，返回非零退出码并明确报告部分完成。 |
| PR 行内评论 | GitCode 使用 `path + position` 模型，`position` 为文件绝对行号。`--line` 校验行号位于 PR diff 中后原样传递；`--position` 跳过 diff 校验。`--side` 仅选择校验侧，不会发送给 GitCode，因此 LEFT 侧锚定仅为尽力支持，不保证准确。不支持选择 commit。 |
| PR review request changes | `--approve` 使用[原生审查接口](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-review/)。与旧版 gc 不同，`--request-changes` 未核实阻塞性审查契约，返回非零且**不再代发评论**；确实只要普通反馈时显式使用 `--comment`。 |
| PR 合并保护 | [合并接口](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge/)没有声明预期 head 或单 PR 的自动合并开关。响应 SHA 不等于写入前提；`--match-head-commit`、`--auto` 和 `--disable-auto` 均拒绝执行，不通过先读后合或轮询代替。 |
| PR 更新、回退和锁定 | [PR API 目录](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/)未核实更新源分支、回退至新 PR、锁定/解锁讨论的写入契约。读到锁定字段或网页有按钮，不等于公开 API 支持写入。 |
| Issue 开发分支、讨论管理与转移 | `gc issue develop N --list` [读取关联分支名](https://atomgit-api-doc.atomgit.com/3.issues/73.get_the_list_of_branches_associated_with_the_issue.html)；[设置接口](https://docs.gitcode.com/en/docs/apis/put-api-v-5-repos-owner-repo-issues-number-related-branches/)接收分支数组，并非原子创建并追加。[Issue API 目录与更新接口](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number/)未核实锁定/解锁、置顶/取消置顶或转移。不会覆盖分支数组、关闭后复制 Issue 或用标签模拟。 |
| Issue 删除 | `gc issue delete` 依赖 GitCode issue 删除行为，该接口目前未在公开 API 中明确记录，后续可能变化。 |
| Draft/ready 操作 | `gc pr ready --undo` 通过 GitCode 的 PR 更新能力切换 draft 状态，但语义可能不同于 GitHub draft PR。 |
| 仓库同步 | `gc repo sync [-b 分支]` 从 fork 的父仓库同步一个远端分支，不做全分支同步。详见[仓库同步](repo-sync.md)；不支持任意 `--source`、`--force` 或同步本地检出。 |
| 仓库归档 | `gc repo view --json isArchived` 根据[仓库详情](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/)读取归档状态；状态未知或字段矛盾时输出 `null`。GitCode 的[组织仓库状态接口](https://docs.gitcode.com/docs/apis/put-api-v-5-org-org-repo-repo-status/)规定整数 `2` 归档、`0` 恢复。gc 尚未实现这两项写操作。 |
| 仓库主题与部署密钥 | GitCode v5 没有仓库 topics 和 deploy-key API，`repo edit --add-topic/--remove-topic` 与 `repo deploy-key` 不可用。 |
| 浏览器流程 | `--web` 会打开对应 GitCode 页面；页面内创建或编辑能力取决于 GitCode Web UI。 |

POSIX 下 token 配置使用私有目录（`0700`）、原子替换文件（`0600`），并拒绝链接存储。HTTP 传输日志及抛出的错误会脱敏当前 token。Windows 文件隐私依赖用户 profile 的 ACL。

squash/title 契约已于 2026-10-30 对照[合并 PR](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge)和[更新 Issue](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number)文档核实；离线契约测试不代表已验证真实 sandbox 兼容性。
