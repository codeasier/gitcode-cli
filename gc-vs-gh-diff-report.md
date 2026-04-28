# gc vs gh CLI 差异分析报告

> 更新时间：2026-04-28（P1 修复后）
> 对比对象：GitHub CLI (`gh`) vs GitCode CLI (`gc`)  
> 校验方式：读取 `src/gitcode_cli/**/*.py` 实现源码，并对照 `gh` 官方文档 (cli.github.com/manual) 逐项比对

---

## 结论

当前 `gc` **没有与 `gh` 完全对齐**。

与上一版报告（2026-04-24）相比，`gc` 在多个方面已有显著改进：

- **`auth login --with-token` 已正确从 stdin 读取 token**
- **`issue list` 已支持 `--milestone`、`--mention`、`--web`，且 `--label` 已改为可重复**
- **`pr list` 已支持 `--assignee`、`--draft`、`--head`、`--web`，且 `--label` 已改为可重复**
- **`pr create` 已支持 `--editor`、`--fill`/`--fill-first`/`--fill-verbose`、`--dry-run`、`--milestone`，且 `--label`/`--reviewer`/`--assignee` 已改为可重复**
- **`pr view` identifier 已可省略，默认当前分支关联 PR**
- **`pr close`/`pr merge`/`pr review`/`pr comment`/`pr edit`/`pr diff`/`pr ready`/`pr reopen` identifier 均已可省略**
- **`issue view` 已支持 `--comments`**
- **`issue comment` 已支持 `--body-file`、`--editor`、`--web`**
- **`issue create --web` 已改为浏览器中创建（与 `gh` 语义一致）**
- **`pr create --web` 已改为浏览器中创建（与 `gh` 语义一致）**
- **`pr review` 已支持 `--comment`、`--request-changes`、`--body`（降级为 PR 评论）**
- **`pr close` 已支持 `--comment`、`--delete-branch`**

本次 P1 修复（2026-04-28）新增的改进：

- **`auth` 命令组已增加 `logout`/`status`/`token` 子命令**
- **`issue create --label` 已改为可重复（与 `issue list` 一致）**
- **`issue close` 已支持 `--comment`/`--reason`**
- **`issue edit` 已支持 `--body-file`/`--milestone`/`--remove-milestone`**
- **`pr view` 已支持 `--comments`**
- **`pr comment` 已支持 `--body-file`/`--editor`/`--web`**
- **`pr merge` 已支持 `--delete-branch`**
- **`pr edit` 已支持 `--body-file`/`--milestone`/`--remove-milestone`**
- **`PullRequestService` 已新增 `list_comments` 方法**

但仍存在以下核心差距：

- **顶层命令组严重不足**：缺少 `repo`、`browse`、`gist`、`release`、`api`、`config`、`status`、`search`、`org`、`project` 等命令组
- **`auth` 命令组仍缺少 `refresh`/`setup-git`/`switch`**
- **Issue 子命令仍有缺失**：`develop`、`lock`/`unlock`、`pin`/`unpin`、`transfer`
- **PR 子命令仍有缺失**：`checks`、`lock`/`unlock`、`revert`、`update-branch`
- **默认文本输出仍比 `gh` 简陋**
- **帮助输出格式仍为 Click 默认，缺少 EXAMPLES / JSON FIELDS 等**
- **`issue status`/`pr status` 语义仍与 `gh` 不一致**

如果以"`gh` 用户几乎无学习成本切换到 `gc`"为标准，当前状态**较上一版有显著改善，但仍不满足**。

---

## 一、顶层命令差异

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 顶层入口 | `gh <command>` | `gc <command>` | 部分对齐 |
| `--version` | ✅ | ✅ | 对齐 |
| `-R, --repo` | ✅ | ✅ | 对齐 |
| `--token`（隐藏） | ❌ | ✅ | GitCode 特有 |
| 帮助输出格式 | 自定义分区式（CORE COMMANDS / GITHUB ACTIONS / ADDITIONAL / EXAMPLES） | Click 默认 `Usage / Options / Commands` | **不对齐** |

### 顶层命令覆盖

| 命令组 | `gh` | `gc` 当前 | 状态 |
|--------|------|-----------|------|
| `auth` | ✅（login/logout/refresh/setup-git/status/switch/token） | ✅（仅 login） | **严重不对齐** |
| `issue` | ✅ | ✅ | 部分对齐 |
| `pr` | ✅ | ✅ | 部分对齐 |
| `repo` | ✅ | ❌ | **缺失** |
| `browse` | ✅ | ❌ | **缺失** |
| `gist` | ✅ | ❌ | **缺失** |
| `release` | ✅ | ❌ | **缺失** |
| `api` | ✅ | ❌ | **缺失** |
| `config` | ✅ | ❌ | **缺失** |
| `status` | ✅ | ❌ | **缺失** |
| `search` | ✅ | ❌ | **缺失** |
| `org` | ✅ | ❌ | **缺失** |
| `project` | ✅ | ❌ | **缺失** |
| `label` | ✅ | ❌ | **缺失** |
| `completion` | ✅ | ❌ | **缺失** |
| `extension` | ✅ | ❌ | **缺失** |
| `alias` | ✅ | ❌ | **缺失** |
| `ruleset` | ✅ | ❌ | **缺失** |
| `secret` | ✅ | ❌ | **缺失** |
| `variable` | ✅ | ❌ | **缺失** |
| `ssh-key` | ✅ | ❌ | **缺失** |
| `gpg-key` | ✅ | ❌ | **缺失** |
| `attestation` | ✅ | ❌ | **缺失** |
| `licenses` | ✅ | ❌ | **缺失** |
| `cache` | ✅ | ❌ | **缺失** |
| `run` | ✅ | ❌ | **缺失** |
| `workflow` | ✅ | ❌ | **缺失** |
| `codespace` | ✅ | ❌ | **缺失** |
| `copilot` | ✅ | ❌ | **缺失** |
| `skill` | ✅ | ❌ | **缺失** |
| `version` | ✅ | ✅ | 对齐 |

对应实现：[cli.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/cli.py)

---

## 二、Auth 命令差异

### 子命令覆盖

| 子命令 | `gh auth` | `gc auth` | 状态 |
|--------|-----------|-----------|------|
| `login` | ✅ | ✅ | 基本对齐 |
| `logout` | ✅ | ✅ | ✅ 对齐 |
| `status` | ✅ | ✅ | ✅ 对齐 |
| `token` | ✅ | ✅ | ✅ 对齐 |
| `refresh` | ✅ | ❌ | **缺失** |
| `setup-git` | ✅ | ❌ | **缺失** |
| `switch` | ✅ | ❌ | **缺失** |

### `auth login`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| `--with-token` | ✅，从 stdin 读取 | ✅，从 stdin 读取 | ✅ 对齐 |
| `--web` | ✅，浏览器登录 | ❌ | **缺失** |
| `--hostname` | ✅，指定 GitHub Enterprise | ❌ | **缺失** |
| `--scopes` | ✅，指定 token 权限范围 | ❌ | **缺失** |
| `--git-protocol` | ✅ | ❌ | **缺失** |
| 交互式登录 | ✅，支持浏览器/设备码/令牌多种方式 | ✅，仅支持令牌输入 | **部分对齐** |
| Token 存储 | 系统密钥库（Keychain/Credential Manager/libsecret） | `~/.config/gc/config.json` 明文 | **不对齐** |

对应实现：[auth.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/auth.py)

---

## 三、Issue 命令差异

### 1. 子命令覆盖

| 子命令 | `gh issue` | `gc issue` | 状态 |
|--------|------------|------------|------|
| `list` / `ls` | ✅ | ✅ | 部分对齐 |
| `view` | ✅ | ✅ | 部分对齐 |
| `create` / `new` | ✅ | ✅ | 部分对齐 |
| `close` | ✅ | ✅ | 基本对齐 |
| `comment` | ✅ | ✅ | 基本对齐 |
| `reopen` | ✅ | ✅ | 基本对齐 |
| `edit` | ✅ | ✅ | 部分对齐 |
| `delete` | ✅ | ✅ | 基本对齐 |
| `status` | ✅ | ✅ | 名称对齐，语义不对齐 |
| `develop` | ✅ | ❌ | **缺失** |
| `lock` / `unlock` | ✅ | ❌ | **缺失** |
| `pin` / `unpin` | ✅ | ❌ | **缺失** |
| `transfer` | ✅ | ❌ | **缺失** |

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 2. `issue list`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `ls` | ✅ | ✅ | 对齐 |
| `-a, --assignee` | ✅ | ✅ | 对齐 |
| `-A, --author` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅，可重复 `<strings>` | ✅，可重复 `multiple=True` | ✅ 对齐 |
| `-L, --limit` | ✅，默认 30 | ✅，默认 30 | ✅ 对齐 |
| `-s, --state` | ✅，默认 "open"，枚举 {open\|closed\|all} | ✅，无默认值 | **部分对齐** |
| `-S, --search` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅，列出可用 JSON FIELDS | ✅，支持逗号分隔字段，无字段清单 | **部分对齐** |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅，Go template 完整语法 | ✅，仅 `{{.field}}` 简化替换 | **部分对齐** |
| `--app` | ✅ | ❌ | **缺失** |
| `--mention` | ✅ | ✅ | ✅ 对齐 |
| `-m, --milestone` | ✅ | ✅ | ✅ 对齐 |
| `-w, --web` | ✅ | ✅ | ✅ 对齐 |
| 默认文本输出 | gh 风格列式展示（含标签） | `#number\tstate\ttitle\tauthor` | **不对齐** |

**gh 默认输出示例**：
```
Issues for owner/repo

#14  Update the remote url if it changed  (bug)
#14  PR commands on a detached head       (enhancement)
#13  Support for GitHub Enterprise        (wontfix)
```

**gc 当前输出**：
```
#14	open	Update the remote url if it changed	author_name
```

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 3. `issue view`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-w, --web` | ✅ | ✅ | 对齐 |
| `-c, --comments` | ✅ | ✅ | ✅ 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| 默认文本输出 | 丰富元数据与结构化布局 | `#num title` + Title/State/Author + Body | **不对齐** |

**gh 默认输出示例**：
```
Issue title
opened by user. 0 comments. (label)

  Issue body

View this issue on GitHub: https://github.com/owner/repo/issues/21
```

**gc 当前输出**：
```
#123 标题

Title:  标题
State:  open
Author: 作者名

Body:
正文内容
```

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 4. `issue create`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `new` | ✅ | ✅ | 对齐 |
| `-t, --title` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅，支持 `-` 代表 stdin | ✅，支持 `-` 代表 stdin | ✅ 对齐 |
| `-a, --assignee` | ✅，支持 `@me` | ✅ | **部分对齐** |
| `-l, --label` | ✅，可重复 | ✅，可重复 `multiple=True` | ✅ 对齐 |
| `-m, --milestone` | ✅ | ✅ | 对齐 |
| `-w, --web` | ✅，浏览器中创建 | ✅，浏览器中创建 | ✅ 对齐 |
| `-e, --editor` | ✅ | ❌ | **缺失** |
| `-p, --project` | ✅ | ❌ | **缺失** |
| `-T, --template` | ✅，模板名称 | ❌ | **缺失** |
| `--recover` | ✅ | ❌ | **缺失** |
| `--json fields` / `-q` / `--template` 输出格式化 | `gh issue create` 不提供 | `gc` 提供 | **差异实现** |

说明：

- `gc issue create --web` 当前行为已与 `gh` 一致：打开浏览器创建页面
- `issue create` 的 `--label` 为单值 `str`，而 `issue list` 的 `--label` 为可重复 `tuple`，**内部不一致**
- `--assignee` 不支持 `@me` 特殊值

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 5. `issue close`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-c, --comment` | ✅ | ✅ | ✅ 对齐 |
| `--duplicate-of` | ✅ | ❌ | **缺失** |
| `-r, --reason` | ✅，枚举 {completed\|not planned\|duplicate} | ✅，枚举 {completed\|not_planned} | **部分对齐** |
| 默认输出 | gh 风格 | `Closed issue #N` | 部分对齐 |

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 6. `issue comment`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-b, --body` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-F, --body-file` | ✅，支持 `-` 代表 stdin | ✅ | ✅ 对齐 |
| `-e, --editor` | ✅ | ✅ | ✅ 对齐 |
| `--edit-last` | ✅ | ❌ | **缺失** |
| `--delete-last` | ✅ | ❌ | **缺失** |
| `--create-if-none` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ✅ | ✅ 对齐 |
| `--yes` | ✅（配合 --delete-last 跳过确认） | ❌ | **缺失** |
| 默认输出 | 评论结果摘要 | 仅输出 comment id | **不对齐** |

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 7. `issue edit`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | 多个 number / URL | 单个 number / URL | **不对齐** |
| `-t, --title` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅ | ✅ | ✅ 对齐 |
| `-a, --add-assignee` | ✅，支持 `@me`/`@copilot` | ✅ | **部分对齐** |
| `-l, --add-label` | ✅ | ✅ | 对齐 |
| `--remove-assignee` | ✅，支持 `@me`/`@copilot` | ✅，映射为 `unassignee` 参数 | **部分对齐** |
| `--remove-label` | ✅ | ✅，映射为 `unset_labels` 参数 | **部分对齐** |
| `-m, --milestone` | ✅ | ✅ | ✅ 对齐 |
| `--remove-milestone` | ✅ | ✅ | ✅ 对齐 |
| `--add-project` | ✅ | ❌ | **缺失** |
| `--remove-project` | ✅ | ❌ | **缺失** |

说明：

- `gh issue edit` 支持同时编辑多个 issue（同一仓库内），`gc` 仅支持单个
- `remove-assignee` 和 `remove-label` 已映射到 API 参数（`unassignee`/`unset_labels`），但需验证 GitCode API 是否真正支持

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

### 8. `issue status`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 语义 | 关注"与当前用户相关"的 issue 状态视图（分配给我的、我提及的、我打开的） | 仅列出当前 repo open issues | **不对齐** |

**gh `issue status` 输出示例**：
```
Relevant issues in owner/repo

Issues assigned to you
  #14  Update the remote url if it changed  (bug)

Issues mentioning you
  #13  Support for GitHub Enterprise  (wontfix)

Issues opened by you
  #8   Add an easier upgrade command  (bug)
```

**gc 当前输出**：
```
GitCode-limited approximation of gh issue status
Repository open issues for owner/repo:
  #123	open	Title
```

对应实现：[issue.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/issue.py)

---

## 四、PR 命令差异

### 1. 子命令覆盖

| 子命令 | `gh pr` | `gc pr` | 状态 |
|--------|---------|---------|------|
| `list` / `ls` | ✅ | ✅ | 部分对齐 |
| `view` | ✅ | ✅ | 部分对齐 |
| `create` / `new` | ✅ | ✅ | 部分对齐 |
| `checkout` | ✅ | ✅ | 部分对齐 |
| `close` | ✅ | ✅ | 基本对齐 |
| `comment` | ✅ | ✅ | 部分对齐 |
| `diff` | ✅ | ✅ | 基本对齐 |
| `edit` | ✅ | ✅ | 部分对齐 |
| `merge` | ✅ | ✅ | 部分对齐 |
| `ready` | ✅ | ✅ | 基本对齐 |
| `reopen` | ✅ | ✅ | 基本对齐 |
| `review` | ✅ | ✅ | 名称对齐，能力部分对齐 |
| `status` | ✅ | ✅ | 名称对齐，语义不对齐 |
| `checks` | ✅ | ❌ | **缺失** |
| `lock` / `unlock` | ✅ | ❌ | **缺失** |
| `revert` | ✅ | ❌ | **缺失** |
| `update-branch` | ✅ | ❌ | **缺失** |

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 2. `pr list`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `ls` | ✅ | ✅ | 对齐 |
| `-A, --author` | ✅ | ✅ | 对齐 |
| `-B, --base` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅，可重复 `<strings>` | ✅，可重复 `multiple=True` | ✅ 对齐 |
| `-L, --limit` | ✅，默认 30 | ✅，默认 30 | ✅ 对齐 |
| `-s, --state` | ✅，默认 "open"，枚举 {open\|closed\|merged\|all} | ✅，无默认值 | **部分对齐** |
| `-S, --search` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `-a, --assignee` | ✅ | ✅ | ✅ 对齐 |
| `-d, --draft` | ✅ | ✅ | ✅ 对齐 |
| `-H, --head` | ✅ | ✅ | ✅ 对齐 |
| `-w, --web` | ✅ | ✅ | ✅ 对齐 |
| `--app` | ✅ | ❌ | **缺失** |
| 默认文本输出 | gh 风格列式展示（含分支名） | `#number\tstate\ttitle\tauthor` | **不对齐** |

**gh 默认输出示例**：
```
Pull requests for owner/repo

#14  Upgrade to Prettier 1.19                           prettier
#14  Extend arrow navigation in lists for MacOS         arrow-nav
#13  Add Support for Windows Automatic Dark Mode        dark-mode
```

**gc 当前输出**：
```
#14	open	Upgrade to Prettier 1.19	author_name
```

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 3. `pr view`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 参数是否可省略 | ✅，默认当前分支关联 PR | ✅，默认当前分支关联 PR | ✅ 对齐 |
| `-w, --web` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `-c, --comments` | ✅ | ✅ | ✅ 对齐 |
| 默认文本输出 | 丰富元数据（含标签、评论数、review 状态） | `#num title` + Title/State/Author/Branch + Body | **不对齐** |

**gh 默认输出示例**：
```
Pull request title
opened by user. 0 comments. (label)

  Pull request body

View this pull request on GitHub: https://github.com/owner/repo/pull/21
```

**gc 当前输出**：
```
#123 标题

Title:  标题
State:  open
Author: 作者名
Branch: feature-branch -> main

Body:
正文内容
```

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 4. `pr create`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `new` | ✅ | ✅ | 对齐 |
| `-t, --title` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅，支持 `-` 代表 stdin | ✅，支持 `-` 代表 stdin | ✅ 对齐 |
| `-B, --base` | ✅，可选 | ✅，可选 | 对齐 |
| `-H, --head` | ✅，可选，支持 `<user>:<branch>` | ✅，可选 | **部分对齐** |
| `-d, --draft` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅，可重复 | ✅，可重复 `multiple=True` | ✅ 对齐 |
| `-r, --reviewer` | ✅，可重复，支持团队 | ✅，可重复 `multiple=True` | **部分对齐** |
| `-a, --assignee` | ✅，可重复，支持 `@me` | ✅，可重复 `multiple=True` | **部分对齐** |
| `-w, --web` | ✅，浏览器中创建 | ✅，浏览器中创建 | ✅ 对齐 |
| `--dry-run` | ✅ | ✅ | ✅ 对齐 |
| `-e, --editor` | ✅ | ✅ | ✅ 对齐 |
| `-f, --fill` | ✅ | ✅ | ✅ 对齐 |
| `--fill-first` | ✅ | ✅ | ✅ 对齐 |
| `--fill-verbose` | ✅ | ✅ | ✅ 对齐 |
| `-m, --milestone` | ✅ | ✅ | ✅ 对齐 |
| `--no-maintainer-edit` | ✅ | ❌ | **缺失** |
| `-p, --project` | ✅ | ❌ | **缺失** |
| `--recover` | ✅ | ❌ | **缺失** |
| `-T, --template` 文件 | ✅ | ❌ | **缺失** |
| `--json / --jq / --template` 输出格式化 | `gh pr create` 不提供 | `gc` 提供 | **差异实现** |
| 自动 fork | ✅，无 push 权限时自动 fork | ❌ | **缺失** |
| `--head` 的 `<user>:<branch>` 语法 | ✅ | ❌ | **缺失** |

说明：

- `gc pr create --web` 当前行为已与 `gh` 一致：打开浏览器创建页面
- `--fill`/`--fill-first`/`--fill-verbose` 已实现，通过 `git log` 获取 commit 信息
- `--dry-run` 已实现，以 JSON 格式打印 payload
- 默认 base 推断逻辑：`gc` 使用 `origin/HEAD`，`gh` 使用 `gh-merge-base` git config 或仓库默认分支

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)、[cli_compat.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/cli_compat.py)

### 5. `pr close`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-c, --comment` | ✅ | ✅ | ✅ 对齐 |
| `-d, --delete-branch` | ✅，删除本地和远程分支 | ✅，仅删除远程分支 | **部分对齐** |

说明：`gc` 删除分支时仅执行 `git push origin --delete <branch>`，不删除本地分支；`gh` 同时删除本地和远程分支。

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 6. `pr comment`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-b, --body` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-F, --body-file` | ✅，支持 `-` 代表 stdin | ✅ | ✅ 对齐 |
| `-e, --editor` | ✅ | ✅ | ✅ 对齐 |
| `--edit-last` | ✅ | ❌ | **缺失** |
| `--delete-last` | ✅ | ❌ | **缺失** |
| `--create-if-none` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ✅ | ✅ 对齐 |
| `--yes` | ✅（配合 --delete-last） | ❌ | **缺失** |
| `--path`, `--position` | ❌ | ✅ | GitCode 特有 |
| 默认输出 | 评论结果摘要 | 仅输出 comment id | **不对齐** |

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 7. `pr merge`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-m, --merge` | ✅ | ✅ | 对齐 |
| `-s, --squash` | ✅ | ✅ | 对齐 |
| `-r, --rebase` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ❌ | **缺失** |
| `-F, --body-file` | ✅ | ❌ | **缺失** |
| `-d, --delete-branch` | ✅ | ✅ | ✅ 对齐 |
| `-t, --subject` | ✅ | ❌ | **缺失** |
| `--admin` | ✅ | ❌ | **缺失** |
| `--auto` | ✅ | ❌ | **缺失** |
| `--disable-auto` | ✅ | ❌ | **缺失** |
| `--match-head-commit` | ✅ | ❌ | **缺失** |
| `--author-email` | ✅ | ❌ | **缺失** |
| 默认行为 | 交互式选择合并策略 | 默认 merge commit | **不对齐** |

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 8. `pr review`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-a, --approve` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ✅ | ✅ 对齐 |
| `-c, --comment` | ✅，原生评论审核 | ✅，**降级为 PR 评论** | **不对齐** |
| `-r, --request-changes` | ✅，原生请求修改 | ✅，**降级为 PR 评论** | **不对齐** |
| `-F, --body-file` | ✅ | ❌ | **缺失** |
| `--force` | ❌ | ✅ | GitCode 特有 |
| 交互式审核 | ✅，无 flag 时进入交互模式 | ❌，必须指定审核类型 | **不对齐** |

说明：`gc pr review --comment` 和 `--request-changes` 由于 GitCode API 限制，降级为普通 PR 评论，并输出警告信息说明 API 不支持此审核类型。

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 9. `pr edit`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-t, --title` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅ | ✅ | ✅ 对齐 |
| `-B, --base` | ✅ | ✅ | 对齐 |
| `-a, --add-assignee` | ✅，支持 `@me`/`@copilot` | ✅ | **部分对齐** |
| `-l, --add-label` | ✅ | ✅ | 对齐 |
| `-r, --add-reviewer` | ✅，支持 `@copilot` | ✅ | **部分对齐** |
| `--remove-assignee` | ✅，支持 `@me`/`@copilot` | ✅ | **部分对齐** |
| `--remove-label` | ✅ | ✅ | 对齐 |
| `--remove-reviewer` | ✅，支持 `@copilot` | ✅ | **部分对齐** |
| `-m, --milestone` | ✅ | ✅ | ✅ 对齐 |
| `--remove-milestone` | ✅ | ✅ | ✅ 对齐 |
| `--add-project` | ✅ | ❌ | **缺失** |
| `--remove-project` | ✅ | ❌ | **缺失** |

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 10. `pr checkout`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `-b, --branch` | ❌ | ✅ | GitCode 特有 |
| 行为 | 智能处理 PR head / fork / 本地分支，支持从 fork 仓库 checkout | 固定 `fetch origin <head>` + `checkout -b` | **不对齐** |

说明：`gh pr checkout` 能智能处理 fork 场景（从 fork 仓库 fetch），`gc` 仅支持同仓库 PR。

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 11. `pr ready`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符可省略 | ✅ | ✅ | ✅ 对齐 |
| `--undo` | ✅，转为 draft | ✅，转为 draft | ✅ 对齐 |

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

### 12. `pr status`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 语义 | 与当前用户相关的 PR 状态视图（创建的、需要 review 的、等待 review 的） | 仅列出当前 repo open PR | **不对齐** |

**gh `pr status` 输出示例**：
```
Relevant pull requests in owner/repo

Current branch
  #14  Upgrade to Prettier 1.19  (draft)

Created by you
  #14  Upgrade to Prettier 1.19  (draft)
  #8   Create keyboard shortcut  (review required)

Review requested
  #13  Add dark mode support  (approved)
```

**gc 当前输出**：
```
Open pull requests in owner/repo  (GitCode API approximation -- user-specific filtering is not available)
  #123	open	Title
```

对应实现：[pr.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/commands/pr.py)

---

## 五、输出与格式化能力差异

### 1. 默认文本输出

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `issue list` 默认输出 | 列式展示，含标签，TTY 友好 | `#number\tstate\ttitle\tauthor` 制表符分隔 | **不对齐** |
| `pr list` 默认输出 | 列式展示，含分支名，TTY 友好 | `#number\tstate\ttitle\tauthor` 制表符分隔 | **不对齐** |
| `issue view` 默认输出 | 标题+元数据行+正文+URL | 标题+Title/State/Author+Body | **不对齐** |
| `pr view` 默认输出 | 标题+元数据行+正文+URL | 标题+Title/State/Author/Branch+Body | **不对齐** |
| `issue create` 默认输出 | Issue URL | Issue URL | ✅ 对齐 |
| `pr create` 默认输出 | PR URL | PR URL | ✅ 对齐 |
| `issue close` 默认输出 | `✓ Closed issue #N` | `Closed issue #N` | **部分对齐** |
| `pr close` 默认输出 | `✓ Closed pull request #N` | `Closed pull request #N` | **部分对齐** |
| `issue comment` 默认输出 | 评论摘要 | 仅输出 comment id | **不对齐** |
| `pr comment` 默认输出 | 评论摘要 | 仅输出 comment id | **不对齐** |
| `pr merge` 默认输出 | 合并结果摘要 | API 返回的 `message` | **部分对齐** |

### 2. `--json / --jq / --template`

| 能力 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `--json fields` | ✅，且 help 会列出完整 JSON FIELDS | ✅，支持逗号分隔字段（含嵌套点号路径），但无字段清单 | **部分对齐** |
| `-q, --jq` | ✅，原生 Go 实现 | ✅，优先 pyjq 库，回退到系统 jq CLI | ✅ 对齐 |
| `-t, --template` | ✅，完整 Go template 语法（条件/循环/管道） | ✅，仅支持简化 `{{.field}}` 替换 | **部分对齐** |
| formatting 帮助体系 | `gh help formatting` | ❌ | **缺失** |
| JSON FIELDS 文档 | ✅，每个命令 help 中列出 | ❌ | **缺失** |

对应实现：[formatters.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/formatters.py)

---

## 六、交互与默认行为差异

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `auth login --with-token` | 从 stdin 读取 token | ✅ 从 stdin 读取 token | ✅ 对齐 |
| `pr create --web` | 浏览器中创建 PR | ✅ 浏览器中创建 PR | ✅ 对齐 |
| `issue create --web` | 浏览器中创建 issue | ✅ 浏览器中创建 issue | ✅ 对齐 |
| 默认 base branch 推断 | gh-merge-base git config / repo default branch | `origin/HEAD`，失败报错 | **不对齐** |
| `pr view` 无参数 | 默认当前分支关联 PR | ✅ 默认当前分支关联 PR | ✅ 对齐 |
| `pr comment / merge / review` 无参数 | 多数场景支持默认当前分支关联 PR | ✅ 支持默认当前分支关联 PR | ✅ 对齐 |
| `pr merge` 交互式选择合并策略 | ✅，无 flag 时交互选择 | ❌，默认 merge commit | **不对齐** |
| `pr review` 交互式审核 | ✅，无 flag 时进入交互模式 | ❌，必须指定审核类型 | **不对齐** |
| 自动 fork | ✅，无 push 权限时自动 fork | ❌ | **缺失** |
| `@me` 特殊值 | ✅，assignee/reviewer 支持 | ❌ | **缺失** |
| `@copilot` 特殊值 | ✅，assignee/reviewer 支持 | ❌ | **缺失** |

对应实现：

- [cli_compat.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/cli_compat.py)
- [utils.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/utils.py)

---

## 七、GitCode 特有差异

这些不是实现缺陷，而是 GitCode API / 产品模型本身和 GitHub 不同，导致无法机械复刻 `gh`：

| 项目 | 说明 |
|------|------|
| Issue create/update API 路径 | GitCode issue create 使用 `/repos/:owner/issues`（路径不含 repo，通过 body 传递），update 使用 `/repos/:owner/issues/{number}` |
| PR comment 模型 | GitCode 采用 `path + position` 模型，而不是 GitHub 常见的 `line / side / commit` 体验 |
| PR review | GitCode review API 仅支持 approve，`--comment` 和 `--request-changes` 降级为普通 PR 评论 |
| 鉴权方式 | GitCode 通过 `access_token` query 参数调用 API，而非 `gh` 的 OAuth 认证流 + 系统密钥库存储 |
| Token 存储 | `gc` 明文存储在 `~/.config/gc/config.json`，`gh` 使用系统密钥库 |
| API 版本 | GitCode API v5（REST），`gh` 主要使用 GitHub API v4（GraphQL）+ v3（REST） |
| `--force` 审核参数 | GitCode 特有，`gh` 无此参数 |
| `--path` / `--position` 评论参数 | GitCode 特有的行内评论模型 |
| `--branch` checkout 参数 | GitCode 特有，`gh` 自动推断本地分支名 |
| `--token` 全局隐藏参数 | GitCode 特有，`gh` 无此参数 |

对应实现：

- [services/issues.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/services/issues.py)
- [services/pulls.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/services/pulls.py)
- [client.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/client.py)
- [config.py](file:///Users/codeasier/Projects/gitcode-cli/src/gitcode_cli/config.py)

---

## 八、最关键的不对齐点

如果目标是"让 `gh` 用户尽量无痛迁移"，当前最关键的问题是：

### P0：语义不一致（误导性兼容）

1. **`issue status` / `pr status` 语义与 `gh` 完全不同**
   - `gh`：展示与当前用户相关的状态视图
   - `gc`：仅列出仓库 open issues/PR
   - 建议：要么实现真正的用户相关视图，要么重命名避免误解

2. **`pr review --comment` / `--request-changes` 降级行为**
   - 虽然参数已存在，但实际降级为普通 PR 评论，与 `gh` 原生审核行为不同
   - 建议：在 help 中明确说明降级行为

3. **`pr merge` 默认行为不同**
   - `gh`：交互式选择合并策略
   - `gc`：默认 merge commit
   - 建议：增加交互式选择

### P1：参数内部不一致

4. **`issue create --label` 为单值，而 `issue list --label` 为可重复**
   - 同一命令组内参数行为不一致，容易造成用户困惑

5. **`--state` 参数缺少默认值和枚举约束**
   - `gh` 默认 "open" 并列出枚举值 {open|closed|all}
   - `gc` 无默认值，help 中未列出可选值

### P2：缺失的高频能力

6. **`auth` 命令组过于单薄**：缺少 `logout`/`status`/`token`
7. **缺少 `repo` 命令组**：`gh repo clone/view/create/fork/list` 是高频操作
8. **缺少 `api` 命令**：`gh api` 是高级用户的核心工具
9. **`pr merge` 缺少 `--delete-branch`**：`gh` 合并后删除分支是常见工作流
10. **`issue close` 缺少 `--comment`/`--reason`**：关闭时添加评论和原因是常见需求

### P3：输出体验差距

11. **默认文本输出仍比 `gh` 简陋**：list 缺少标签/分支名，view 缺少评论数/URL
12. **帮助输出格式**：缺少 EXAMPLES、JSON FIELDS、默认值说明
13. **`--template` 仅支持简单替换**：不支持条件/循环/管道

---

## 九、整体评估

| 维度 | 上一版评价 | 当前评价 | 变化 |
|------|-----------|---------|------|
| 命令命名相似度 | 较高 | 较高 | → |
| 子命令覆盖度 | 中等偏低 | 中等 | ↑ |
| 参数名相似度 | 中等 | 较高 | ↑ |
| 参数完整度 | 偏低 | 中等偏高 | ↑ |
| 行为兼容度 | 偏低 | 中等 | ↑ |
| 输出格式兼容度 | 偏低 | 偏低 | → |
| 整体 gh 对齐度 | **约 4/10** | **约 6/10** | ↑ |

### 改进亮点

- `pr create` 参数覆盖已基本对齐 `gh`（`--fill`/`--editor`/`--dry-run`/`--milestone` 均已实现）
- `pr list` 参数覆盖已对齐 `gh`（`--assignee`/`--draft`/`--head`/`--web` 均已实现）
- `issue list` 参数覆盖已对齐 `gh`（`--milestone`/`--mention`/`--web` 均已实现）
- `--web` 语义已修正为浏览器中创建（与 `gh` 一致）
- `auth login --with-token` 已正确从 stdin 读取
- PR 标识符已支持可省略（默认当前分支）

### 仍需改进

- 顶层命令组覆盖严重不足
- `auth` 命令组过于单薄
- 默认文本输出体验差距明显
- `issue status`/`pr status` 语义与 `gh` 不一致
- `issue create --label` 与 `issue list --label` 行为不一致

---

## 十、建议优先级

### P0：修正语义不一致（避免误导 `gh` 用户）

1. 修正 `issue status` / `pr status` 语义，或重命名避免误解
2. 在 `pr review --comment` / `--request-changes` 的 help 中明确说明降级行为
3. 修正 `pr merge` 增加交互式合并策略选择
4. 统一 `issue create --label` 为可重复（与 `issue list` 一致）

### P1：补齐高频缺失能力

1. ~~`auth` 增加 `logout`/`status`/`token` 子命令~~ ✅ 已完成
2. `repo` 命令组：至少实现 `clone`/`view`/`create`/`fork`/`list`
3. `api` 命令：实现通用 API 调用能力
4. ~~`pr merge` 增加 `--delete-branch`~~ ✅ 已完成
5. ~~`issue close` 增加 `--comment`/`--reason`~~ ✅ 已完成
6. ~~`pr view` 增加 `--comments`~~ ✅ 已完成
7. ~~`pr comment` 增加 `--body-file`/`--editor`/`--web`~~ ✅ 已完成
8. ~~`issue edit` 增加 `--body-file`/`--milestone`/`--remove-milestone`~~ ✅ 已完成
9. ~~`pr edit` 增加 `--body-file`/`--milestone`/`--remove-milestone`~~ ✅ 已完成

### P2：提升输出体验

1. 改善 `issue list`/`pr list` 默认文本输出（增加标签、分支名等）
2. 改善 `issue view`/`pr view` 默认文本输出（增加评论数、URL 等）
3. 改善 `issue comment`/`pr comment` 默认输出（从仅 id 改为评论摘要）
4. help 中写清默认值、枚举值、示例
5. 对 `--json` 输出补充字段清单
6. 增强 `--template` 支持条件/循环语法
7. 增加 `gh help formatting` 等价的格式化帮助

### P3：扩展命令覆盖

1. `issue develop`/`lock`/`unlock`/`pin`/`unpin`/`transfer`
2. `pr checks`/`lock`/`unlock`/`revert`/`update-branch`
3. `browse`/`gist`/`release`/`search`/`config`/`completion`/`extension`/`alias`
4. `@me`/`@copilot` 特殊值支持
5. 自动 fork 能力

---

## 十一、最终判断

当前 `gc` 在核心 issue/pr 工作流上已取得显著进步，参数覆盖度和行为兼容度较上一版有明显提升。

更准确的说法应当是：

> `gc` 在命令命名、参数设计和核心工作流上已较好地参考了 `gh`，issue/pr 的基础创建、查看、列表、编辑、合并、关闭等流程已基本可用，`auth` 命令组已覆盖登录/登出/状态/令牌四个核心子命令。但在顶层命令覆盖（repo/api/config 等）、默认文本输出体验、`status` 命令语义、以及高级交互能力（自动 fork、交互式合并策略、@me 特殊值）等方面，与 `gh` 仍有明显差距。
