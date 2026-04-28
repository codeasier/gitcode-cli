# 路线图 / 未来改进

> 本文档记录基于 `gc` (GitCode CLI) 与 `gh` (GitHub CLI) 差异而计划开发的功能。

---

## 高优先级

### 1. Issue 评论管理

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

### 2. PR 评审增强

**当前差距：**
- `gc pr review` 现已支持 `--approve`、`--comment`、`--request-changes`（降级为 PR 评论）
- 但 GitCode 原生评审 API 与 GitHub 相比可能有局限

**计划实现：**
- 探索 GitCode 实际评审端点能力
- 若 GitCode 支持原生评论/请求变更评审，实现直接 API 调用
- 改进评审正文文本支持

---

## 中优先级

### 3. 交互式 PR 选择

**当前差距：**
- `gc pr checkout` 需显式 PR 标识符（现已可选，但无交互选择）
- `gh pr checkout`（无参数）交互式显示最近 10 个 PR 供选择

**计划实现：**
- 无参数时添加交互式选择功能
- 显示最近打开的 PR 编号列表供用户选择

---

### 4. PR CI 状态

**当前差距：**
- 无 `gc pr checks` 命令
- `gh pr checks` 显示 PR 的 CI 状态

---

### 5. Issue 关闭原因

**当前差距：**
- `issue close` 缺少 `--reason` 标志
- `gh` 支持：`completed`、`not_planned`、`duplicate`

---

## 低优先级

### 6. Issue 锁定/解锁/置顶/取消置顶

**当前差距：**
- 缺少 `issue lock/unlock/pin/unpin` 命令

---

### 7. PR 锁定/解锁

**当前差距：**
- 缺少 `pr lock/unlock` 命令

---

### 8. Issue 转移

**当前差距：**
- 缺少 `issue transfer` 命令（跨仓库转移 Issue）

---

### 9. PR 回退

**当前差距：**
- 缺少 `pr revert` 命令

---

### 10. PR 更新分支

**当前差距：**
- 缺少 `pr update-branch` 命令

---

### 11. PR 合并增强

**当前差距：**
- `pr merge` 缺少 `--delete-branch`、`--admin`、`--auto` 标志