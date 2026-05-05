# 路线图 / 未来改进

> 本文档记录基于 `gc` (GitCode CLI) 与 `gh` (GitHub CLI) 差异而计划开发的剩余功能。

---

## 高优先级

### 1. PR 评审增强

**当前差距：**
- `gc pr review` 现已支持 `--approve`、`--comment`、`--request-changes`（降级为 PR 评论）
- 但 GitCode 原生评审 API 与 GitHub 相比可能有局限

**计划实现：**
- 探索 GitCode 实际评审端点能力
- 若 GitCode 支持原生评论/请求变更评审，实现直接 API 调用
- 改进评审正文文本支持

---

## 中优先级

### 2. 交互式 PR 选择

**当前差距：**
- `gc pr checkout` 需显式 PR 标识符（现已可选，但无交互选择）
- `gh pr checkout`（无参数）交互式显示最近 10 个 PR 供选择

**计划实现：**
- 无参数时添加交互式选择功能
- 显示最近打开的 PR 编号列表供用户选择

---

### 3. PR CI 状态

**当前差距：**
- 无 `gc pr checks` 命令
- `gh pr checks` 显示 PR 的 CI 状态

---

## 低优先级

### 4. Issue 锁定/解锁/置顶/取消置顶

**当前差距：**
- 缺少 `issue lock/unlock/pin/unpin` 命令

---

### 5. PR 锁定/解锁

**当前差距：**
- 缺少 `pr lock/unlock` 命令

---

### 6. Issue 转移

**当前差距：**
- 缺少 `issue transfer` 命令（跨仓库转移 Issue）

---

### 7. PR 回退

**当前差距：**
- 缺少 `pr revert` 命令

---

### 8. PR 更新分支

**当前差距：**
- 缺少 `pr update-branch` 命令
