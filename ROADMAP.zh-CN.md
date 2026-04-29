## 高优先级

### 1. Issue 评论管理（差异4）

**当前差距：**
- `gc issue comment` 和 `gc pr comment` 缺少编辑/删除已有评论的能力
- `gh` 支持：
  - `--edit-last`：编辑当前用户的最后一条评论
  - `--delete-last`：删除当前用户的最后一条评论
  - `--create-if-none`：无评论时创建新评论（配合 `--edit-last`）

**计划实现：**
- 向 `issue comment` 和 `pr comment` 添加 `--edit-last` 标志
- 添加 `--delete-last` 标志及确认提示（`--yes` 跳过）
- 添加 `--create-if-none` 标志用于条件创建

**API 说明：**
- GitCode 可能使用类似的端点结构：`PATCH/DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}`
- 需获取评论，按当前用户过滤，取最后一条

---

### 2. PR 评审增强（差异5）

**当前差距：**
- `gc pr review` 现已支持 `--approve`、`--comment`、`--request-changes`（降级为 PR 评论）
- 但 GitCode 原生评审 API 与 GitHub 相比可能有局限

**计划实现：**
- 探索 GitCode 实际评审端点能力
- 若 GitCode 支持原生评论/请求变更评审，实现直接 API 调用
- 改进评审正文文本支持

---

## 中优先级（进行中）

### 3. PR 标识符可选（差异1）

**当前状态：**
- ✅ `pr view`、`pr merge`、`pr comment`、`pr review` — 标识符可选（从当前分支推断）
- ❌ `pr close`、`pr reopen`、`pr edit`、`pr diff`、`pr checkout`、`pr ready` — 标识符仍必填

**计划实现：**
- 使剩余 PR 命令的标识符可选
- 所有命令应支持：编号 / URL / 分支名 / 当前分支推断

---

### 4. PR 创建 --fill（差异2）

**当前状态：**
- ✅ `--editor` 已实现
- ❌ `--fill` 未实现

**计划实现：**
- 添加 `--fill` 标志，从 git commit 信息自动填充标题和正文
- 支持 `--fill-first`（使用首个 commit）和 `--fill-verbose`（使用所有 commits）
- 实现：解析当前分支的 `git log` 输出

---

### 5. PR 编辑移除操作（差异3）

**当前状态：**
- ❌ `issue edit` 尚未对齐 `gh` 的 `--remove-assignee` / `--remove-label`
- ❌ `pr edit` 缺少 `--remove-assignee`、`--remove-label`、`--remove-reviewer`

**计划实现：**
- 待确认 GitCode API 对移除 assignee/label 的正式契约后，再补齐 `issue edit` / `pr edit` 的移除标志
- 确保所有移除操作正确传递给 API

---

## 低优先级

### 6. 交互式 PR 选择

**当前差距：**
- `gc pr checkout` 需显式 PR 标识符
- `gh pr checkout`（无参数）交互式显示最近 10 个 PR 供选择

---

### 7. PR CI 状态

**当前差距：**
- 无 `gc pr checks` 命令
- `gh pr checks` 显示 PR 的 CI 状态

---

### 8. Issue 锁定/解锁/置顶/取消置顶

**当前差距：**
- 缺少 `issue lock/unlock/pin/unpin` 命令

---

### 9. PR 锁定/解锁

**当前差距：**
- 缺少 `pr lock/unlock` 命令

---

### 10. Issue 转移

**当前差距：**
- 缺少 `issue transfer` 命令（跨仓库转移 Issue）

---

### 11. PR 回退

**当前差距：**
- 缺少 `pr revert` 命令

---

### 12. PR 更新分支

**当前差距：**
- 缺少 `pr update-branch` 命令

---

## 已完成

- ✅ PR 命令：`view`、`merge`、`comment`、`review` 支持可选标识符（当前分支推断）
- ✅ `pr create` 支持 `--editor` 和 `--dry-run`
- ✅ `pr review` 支持 `--comment` 和 `--request-changes`（降级处理）
- ✅ 改进 `issue view`、`pr view`、`issue list`、`pr list` 默认输出格式
- ✅ 向 `issue list`、`pr list` 添加 `--web` 标志用于浏览器查看
