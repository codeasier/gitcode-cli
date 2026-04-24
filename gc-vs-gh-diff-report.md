# gc vs gh CLI 差异分析报告

> 更新时间：2026-04-24  
> 对比对象：GitHub CLI (`gh`) vs GitCode CLI (`gc`)  
> 校验方式：读取 `src/gitcode_cli/**/*.py` 实现，并实际对比 `python -m gitcode_cli.cli --help` 与 `gh --help` 输出

---

## 结论

当前 `gc` **没有与 `gh` 完全对齐**。

它目前更准确的定位是：

- **命令分组与部分参数名参考了 `gh`**
- **核心 issue / pr 流程已有基础实现**
- **但在子命令覆盖、参数完整度、默认行为、交互语义、帮助输出格式、默认文本输出上，与 `gh` 仍有明显差距**

如果以“`gh` 用户几乎无学习成本切换到 `gc`”为标准，当前状态**还不满足**。

---

## 一、顶层命令差异

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 顶层入口 | `gh <command>` | `gc <command>` | 部分对齐 |
| 顶层命令覆盖 | `auth issue pr repo status api ...` | `auth issue pr version` | **不对齐** |
| `--version` | ✅ | ✅ | 部分对齐 |
| `-R, --repo` | ✅ | ✅ | 对齐 |
| 帮助输出格式 | 自定义分区式（CORE COMMANDS / EXAMPLES / HELP TOPICS） | Click 默认 `Usage / Options / Commands` | **不对齐** |

对应实现：`src/gitcode_cli/cli.py:13`

---

## 二、Issue 命令差异

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

对应实现：`src/gitcode_cli/commands/issue.py:10`

### 2. `issue list`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `ls` | ✅ | ✅ | 对齐 |
| `-a, --assignee` | ✅ | ✅ | 对齐 |
| `-A, --author` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅，可重复 | ✅，但当前为单值文本 | **部分对齐** |
| `-L, --limit` | ✅，默认 30 | ✅，但 help 未体现默认值 | **部分对齐** |
| `-s, --state` | ✅ | ✅ | 对齐 |
| `-S, --search` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅，支持逗号分隔字段 | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `--app` | ✅ | ❌ | **缺失** |
| `--mention` | ✅ | ❌ | **缺失** |
| `-m, --milestone` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ❌ | **缺失** |
| 默认文本输出 | gh 风格列式展示 | `#number\tstate\ttitle` | **不对齐** |

对应实现：`src/gitcode_cli/commands/issue.py:15`

### 3. `issue view`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-w, --web` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `-c, --comments` | ✅ | ❌ | **缺失** |
| 默认文本输出 | 丰富元数据与结构化布局 | 仅 `#num title + body` | **不对齐** |

对应实现：`src/gitcode_cli/commands/issue.py:57`

### 4. `issue create`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `new` | ✅ | ✅ | 对齐 |
| `-t, --title` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅ | ✅ | 部分对齐 |
| `-a, --assignee` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅ | ✅，但单值 | 部分对齐 |
| `-m, --milestone` | ✅ | ✅ | 对齐 |
| `-w, --web` | ✅ | ✅，但语义不同 | **不对齐** |
| `-e, --editor` | ✅ | ❌ | **缺失** |
| `-p, --project` | ✅ | ❌ | **缺失** |
| `-T, --template` | ✅ | ❌ | **缺失** |
| `--json fields` / `-q` / `--template` 输出格式化 | `gh issue create` 不提供这套 | `gc` 提供 | **差异实现** |

说明：

- `gc issue create --web` 当前行为是**先创建，再打开创建后的 issue URL**，不是 `gh` 的 web 创建流程。  
- `body-file` 当前直接读文件内容，未确认支持 `-` 代表 stdin。

对应实现：`src/gitcode_cli/commands/issue.py:95`

### 5. `issue close`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-c, --comment` | ✅ | ❌ | **缺失** |
| `--duplicate-of` | ✅ | ❌ | **缺失** |
| `-r, --reason` | ✅ | ❌ | **缺失** |
| 默认输出 | gh 风格 | `Closed issue #N` | 部分对齐 |

对应实现：`src/gitcode_cli/commands/issue.py:141`

### 6. `issue comment`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL | number / URL | 对齐 |
| `-b, --body` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-F, --body-file` | ✅ | ❌ | **缺失** |
| `-e, --editor` | ✅ | ❌ | **缺失** |
| `--edit-last` / `--delete-last` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ❌ | **缺失** |
| 默认输出 | 评论结果摘要 | 仅输出 comment id | **不对齐** |

对应实现：`src/gitcode_cli/commands/issue.py:158`

### 7. `issue edit`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| `-t, --title` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-a, --add-assignee` | ✅ | ✅ | 对齐 |
| `-l, --add-label` | ✅ | ✅ | 对齐 |
| `--remove-assignee` | ✅ | ✅，但当前未实际生效 | **不对齐** |
| `--remove-label` | ✅ | ✅，但当前未实际生效 | **不对齐** |

说明：`remove_assignee` 和 `remove_label` 参数虽然声明了，但实现中未使用。  
对应实现：`src/gitcode_cli/commands/issue.py:194`

### 8. `issue status`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 语义 | 关注“与当前用户相关”的 issue 状态视图 | 仅列出当前 repo open issues | **不对齐** |

对应实现：`src/gitcode_cli/commands/issue.py:255`

---

## 三、PR 命令差异

### 1. 子命令覆盖

| 子命令 | `gh pr` | `gc pr` | 状态 |
|--------|---------|---------|------|
| `list` / `ls` | ✅ | ✅ | 部分对齐 |
| `view` | ✅ | ✅ | 部分对齐 |
| `create` / `new` | ✅ | ✅ | 部分对齐 |
| `checkout` | ✅ | ✅ | 部分对齐 |
| `close` | ✅ | ✅ | 部分对齐 |
| `comment` | ✅ | ✅ | 部分对齐 |
| `diff` | ✅ | ✅ | 基本对齐 |
| `edit` | ✅ | ✅ | 部分对齐 |
| `merge` | ✅ | ✅ | 部分对齐 |
| `ready` | ✅ | ✅ | 基本对齐 |
| `reopen` | ✅ | ✅ | 基本对齐 |
| `review` | ✅ | ✅ | 名称对齐，能力不对齐 |
| `status` | ✅ | ✅ | 名称对齐，语义不对齐 |
| `checks` | ✅ | ❌ | **缺失** |
| `lock` / `unlock` | ✅ | ❌ | **缺失** |
| `revert` | ✅ | ❌ | **缺失** |
| `update-branch` | ✅ | ❌ | **缺失** |

对应实现：`src/gitcode_cli/commands/pr.py:19`

### 2. `pr list`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `ls` | ✅ | ✅ | 对齐 |
| `-A, --author` | ✅ | ✅ | 对齐 |
| `-B, --base` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅，可重复 | ✅，但单值文本 | **部分对齐** |
| `-L, --limit` | ✅，默认 30 | ✅，未体现默认值 | **部分对齐** |
| `-s, --state` | ✅ | ✅ | 对齐 |
| `-S, --search` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `-a, --assignee` | ✅ | ❌ | **缺失** |
| `-d, --draft` | ✅ | ❌ | **缺失** |
| `-H, --head` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ❌ | **缺失** |
| 默认文本输出 | gh 风格列式展示 | `#number\tstate\ttitle` | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:24`

### 3. `pr view`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| 参数是否可省略 | gh 可省略，默认当前分支关联 PR | 当前必填 | **不对齐** |
| `-w, --web` | ✅ | ✅ | 对齐 |
| `--json fields` | ✅ | ✅ | 部分对齐 |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅ | ✅ | 部分对齐 |
| `-c, --comments` | ✅ | ❌ | **缺失** |
| 默认文本输出 | 丰富元数据 | 仅 `#num title + body` | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:66`

### 4. `pr create`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 别名 `new` | ✅ | ✅ | 对齐 |
| `-t, --title` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-b, --body` | ✅ | ✅ | 对齐 |
| `-F, --body-file` | ✅ | ✅ | 部分对齐 |
| `-B, --base` | ✅，可选 | ✅，可选 | 对齐 |
| `-H, --head` | ✅，可选 | ✅，可选 | 对齐 |
| `-d, --draft` | ✅ | ✅ | 对齐 |
| `-l, --label` | ✅ | ✅，但单值 | 部分对齐 |
| `-r, --reviewer` | ✅ | ✅，但单值 | 部分对齐 |
| `-a, --assignee` | ✅ | ✅，但单值 | 部分对齐 |
| `-w, --web` | ✅ | ✅，但语义不同 | **不对齐** |
| `--dry-run` | ✅ | ❌ | **缺失** |
| `-e, --editor` | ✅ | ❌ | **缺失** |
| `-f, --fill` / `--fill-first` / `--fill-verbose` | ✅ | ❌ | **缺失** |
| `-m, --milestone` | ✅ | ❌ | **缺失** |
| `--no-maintainer-edit` | ✅ | ❌ | **缺失** |
| `-p, --project` | ✅ | ❌ | **缺失** |
| `--recover` | ✅ | ❌ | **缺失** |
| `-T, --template` 文件 | ✅ | ❌ | **缺失** |
| `--json / --jq / --template` 输出格式化 | `gh pr create` 不提供这套 | `gc` 提供 | **差异实现** |

说明：

- 当前 `gc pr create --web` 是**创建成功后打开 PR URL**，不是 `gh` 的浏览器创建流程。  
- 当前默认 base 推断逻辑是读取 `origin/HEAD`，失败后回退为 `master`，与 `gh` 的 merge-base / repo default branch 逻辑不一致。

对应实现：`src/gitcode_cli/commands/pr.py:101`、`src/gitcode_cli/utils.py:35`

### 5. `pr close`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch | number / URL / branch | 对齐 |
| `-c, --comment` | ✅ | ✅ | 对齐 |
| `-d, --delete-branch` | ✅ | ✅ | 部分对齐 |

说明：当前 `gc` 删除分支时直接执行 `git push origin --delete <branch>`，实现比 `gh` 简化很多。  
对应实现：`src/gitcode_cli/commands/pr.py:170`

### 6. `pr comment`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch，且通常可省略 | number / URL / branch，但当前必填 | **部分对齐** |
| `-b, --body` | ✅，可省略并交互提示 | ✅，可省略并交互提示 | 对齐 |
| `-F, --body-file` | ✅ | ❌ | **缺失** |
| `-e, --editor` | ✅ | ❌ | **缺失** |
| `--edit-last` / `--delete-last` | ✅ | ❌ | **缺失** |
| `-w, --web` | ✅ | ❌ | **缺失** |
| `--path`, `--position` | ❌ | ✅ | GitCode 特有 |
| 默认输出 | 评论结果摘要 | 仅输出 comment id | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:217`

### 7. `pr merge`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch，通常可省略 | number / URL / branch，但当前必填 | **部分对齐** |
| `-m, --merge` | ✅ | ✅ | 对齐 |
| `-s, --squash` | ✅ | ✅ | 对齐 |
| `-r, --rebase` | ✅ | ✅ | 对齐 |
| `-b, --body` / `-F, --body-file` | ✅ | ❌ | **缺失** |
| `-d, --delete-branch` | ✅ | ❌ | **缺失** |
| `-t, --subject` | ✅ | ❌ | **缺失** |
| `--admin` / `--auto` / `--disable-auto` | ✅ | ❌ | **缺失** |

对应实现：`src/gitcode_cli/commands/pr.py:200`

### 8. `pr review`

| 参数/能力 | `gh` | `gc` 当前 | 状态 |
|-----------|------|-----------|------|
| 标识符支持 | number / URL / branch，通常可省略 | number / URL / branch，但当前必填 | **部分对齐** |
| `-a, --approve` | ✅ | ✅ | 对齐 |
| `-b, --body` | ✅ | ❌ | **缺失** |
| `-c, --comment` | ✅ | ❌ | **缺失** |
| `-r, --request-changes` | ✅ | ❌ | **缺失** |
| `--force` | ❌ | ✅ | GitCode 特有 |
| 整体能力 | approve / comment / request changes | 当前仅支持 approve | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:237`

### 9. `pr checkout`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 行为 | 更智能地处理 PR head / fork / 本地分支 | 固定 `fetch origin <head>` + `checkout -b` | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:324`

### 10. `pr status`

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| 命令名 | ✅ | ✅ | 对齐 |
| 语义 | 与当前用户相关的 PR 状态视图 | 仅列出当前 repo open PR | **不对齐** |

对应实现：`src/gitcode_cli/commands/pr.py:360`

---

## 四、输出与格式化能力差异

### 1. 默认文本输出

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `issue list` 默认输出 | 更完整、TTY 友好 | `#number\tstate\ttitle` | **不对齐** |
| `pr list` 默认输出 | 更完整、TTY 友好 | `#number\tstate\ttitle` | **不对齐** |
| `issue view` 默认输出 | 包含更多元数据 | 仅标题和正文 | **不对齐** |
| `pr view` 默认输出 | 包含更多元数据 | 仅标题和正文 | **不对齐** |

### 2. `--json / --jq / --template`

| 能力 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `--json fields` | ✅，且 help 会列出 JSON FIELDS | ✅，支持逗号分隔字段，但无字段清单 | **部分对齐** |
| `-q, --jq` | ✅ | ✅ | 对齐 |
| `-t, --template` | ✅，Go template 生态更完整 | ✅，仅支持简化 `{{.field}}` 替换 | **部分对齐** |
| formatting 帮助体系 | `gh help formatting` | ❌ | **缺失** |

对应实现：`src/gitcode_cli/formatters.py:10`

---

## 五、交互与默认行为差异

| 项目 | `gh` | `gc` 当前 | 状态 |
|------|------|-----------|------|
| `auth login --with-token` | 从 stdin 读取 token | 参数存在，但当前未实现 stdin 读取 | **不对齐** |
| `pr create --web` | 浏览器中创建 PR | 创建完成后打开 PR 页面 | **不对齐** |
| `issue create --web` | 浏览器中创建 issue | 创建完成后打开 issue 页面 | **不对齐** |
| 默认 base branch 推断 | gh-merge-base / repo default branch | `origin/HEAD`，失败回退 `master` | **不对齐** |
| `pr view` 无参数 | 默认当前分支关联 PR | 当前必须显式传 identifier | **不对齐** |
| `pr comment / merge / review` 无参数 | 多数场景支持默认当前分支关联 PR | 当前必须显式传 identifier | **不对齐** |

对应实现：

- `src/gitcode_cli/commands/auth.py:12`
- `src/gitcode_cli/commands/pr.py:101`
- `src/gitcode_cli/commands/issue.py:95`
- `src/gitcode_cli/utils.py:35`

---

## 六、GitCode 特有差异

这些不是实现缺陷，而是 GitCode API / 产品模型本身和 GitHub 不同，导致无法机械复刻 `gh`：

| 项目 | 说明 |
|------|------|
| Issue create/update API 路径 | GitCode issue create/update 使用 `/repos/:owner/issues`，并在 body 中携带 `repo` |
| PR comment 模型 | GitCode 采用 `path + position` 模型，而不是 GitHub 常见的 `line / side / commit` 体验 |
| PR review | 当前 GitCode review API 能力与 `gh` 不同，因此 `gc pr review` 仅实现 `--approve`，并额外暴露了 `--force` |
| 鉴权方式 | GitCode 当前客户端通过 `access_token` query 参数调用 API，而非 `gh` 常见的 GitHub 认证流 |

对应实现：

- `src/gitcode_cli/services/issues.py:17`
- `src/gitcode_cli/services/pulls.py:30`
- `src/gitcode_cli/commands/pr.py:237`
- `src/gitcode_cli/client.py:21`

---

## 七、最关键的不对齐点

如果目标是“让 `gh` 用户尽量无痛迁移”，当前最关键的问题是：

1. **同名参数语义不一致**
   - 例如 `pr create --web`
   - 例如 `auth login --with-token`

2. **同名命令语义不一致**
   - 例如 `issue status`
   - 例如 `pr status`

3. **暴露了参数但未真正生效**
   - `issue edit --remove-assignee`
   - `issue edit --remove-label`

4. **帮助与默认输出远未达到 `gh` 体验**
   - help 文案缺少默认值、JSON FIELDS、EXAMPLES
   - 默认输出比 `gh` 简陋很多

5. **常用参数和子命令仍缺失不少**
   - `issue develop / lock / transfer`
   - `pr checks / revert / update-branch`
   - `--fill / --editor / --body-file / --web` 等高级交互能力缺失或语义不同

---

## 八、整体评估

| 维度 | 评价 |
|------|------|
| 命令命名相似度 | 较高 |
| 子命令覆盖度 | 中等偏低 |
| 参数名相似度 | 中等 |
| 行为兼容度 | 偏低 |
| 输出格式兼容度 | 偏低 |
| 整体 gh 对齐度 | **约 4/10** |

---

## 九、建议优先级

### P0：先修“伪兼容”问题

1. 修正 `auth login --with-token`，真正从 stdin 读取 token
2. 修正 `issue edit --remove-assignee / --remove-label` 未生效问题
3. 明确区分 `--web` 的实际语义，避免与 `gh` 误导性同名
4. 修正 `pr status` / `issue status` 的语义，或调整命名避免误解
5. 修正默认 base branch fallback 为 `master` 的逻辑

### P1：补齐高频参数与子命令

1. `issue list` 增加 `--web --milestone --mention`
2. `pr list` 增加 `--assignee --draft --head --web`
3. `pr create` 增加 `--fill --editor --dry-run --milestone`
4. `pr review` 增加 comment / request changes 能力
5. 让 `--label / --reviewer / --assignee` 支持多值或 repeatable

### P2：提升帮助和输出体验

1. help 中写清默认值、枚举值、示例
2. 对 `--json` 输出补充字段说明
3. 改善 list / view 默认文本输出
4. 增加更接近 `gh` 的 formatting 说明

---

## 十、最终判断

当前 `gc` 已经具备基础 issue / pr CLI 能力，但**还不能称为“与 `gh` 完全对齐”**。

更准确的说法应当是：

> `gc` 在命令命名和部分 flags 上参考了 `gh`，但仍未实现 `gh` 级别的命令覆盖、参数兼容、交互行为和输出体验。
