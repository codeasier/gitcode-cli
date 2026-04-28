# Tasks

- [x] Task 1: 创建 git worktree 并切换到修复分支
  - [x] SubTask 1.1: 在 `.worktrees/` 目录下创建 worktree `fix-issue-12-keyerror-number`
  - [x] SubTask 1.2: 从 main 分支创建 `fix/issue-12-keyerror-number` 分支

- [x] Task 2: 在 `utils.py` 中新增 `safe_number` 辅助函数
  - [x] SubTask 2.1: 实现 `safe_number(item: Any, fallback: int | str) -> int | str` 函数
  - [x] SubTask 2.2: 在 `utils.py` 的导出中添加该函数

- [x] Task 3: 修复 `commands/pr.py` 中的 6 处 `item['number']` 访问
  - [x] SubTask 3.1: 导入 `safe_number`
  - [x] SubTask 3.2: 修复 `pr_close` (line 280)
  - [x] SubTask 3.3: 修复 `pr_reopen` (line 415)
  - [x] SubTask 3.4: 修复 `pr_edit` (line 480)
  - [x] SubTask 3.5: 修复 `pr_ready` (lines 534, 536)
  - [x] SubTask 3.6: 修复 `pr_status` (line 552)

- [x] Task 4: 修复 `commands/issue.py` 中的 4 处 `item['number']` 访问
  - [x] SubTask 4.1: 导入 `safe_number`
  - [x] SubTask 4.2: 修复 `issue_close` (line 220)
  - [x] SubTask 4.3: 修复 `issue_reopen` (line 271)
  - [x] SubTask 4.4: 修复 `issue_edit` (line 329)
  - [x] SubTask 4.5: 修复 `issue_status` (line 361)

- [x] Task 5: 补充测试用例
  - [x] SubTask 5.1: 为 `safe_number` 函数编写单元测试 (6 个)
  - [x] SubTask 5.2: 为 `pr close` 添加 API 响应缺少 `number` 的测试 (2 个)
  - [x] SubTask 5.3: 为 `pr reopen` 添加 API 响应缺少 `number` 的测试 (1 个)
  - [x] SubTask 5.4: 为 `pr edit` 添加 API 响应缺少 `number` 的测试 (1 个)
  - [x] SubTask 5.5: 为 `pr ready` 添加 API 响应缺少 `number` 的测试 (2 个)
  - [x] SubTask 5.6: 为 `issue close` 添加 API 响应缺少 `number` 的测试 (2 个)
  - [x] SubTask 5.7: 为 `issue reopen` 添加 API 响应缺少 `number` 的测试 (1 个)
  - [x] SubTask 5.8: 为 `issue edit` 添加 API 响应缺少 `number` 的测试 (1 个)

- [x] Task 6: 运行完整测试和代码质量检查
  - [x] SubTask 6.1: 运行 `python -m pytest tests/unit/` 确保全部通过 (266 passed)
  - [x] SubTask 6.2: 运行 `python -m ruff check src/ tests/` 确保 lint 通过
  - [x] SubTask 6.3: 运行 `python -m ruff format --check src/ tests/` 确保格式通过
  - [x] SubTask 6.4: 运行 `python -m basedpyright src/` 确保类型检查通过 (0 errors)
  - [x] SubTask 6.5: 确认测试覆盖率 >= 90% (91.76%)

- [x] Task 7: 提交代码并创建 PR
  - [x] SubTask 7.1: 使用 conventional commit 格式提交代码
  - [x] SubTask 7.2: 使用 `gh pr create` 创建 PR，填写 PR 模板内容
  - [x] SubTask 7.3: PR 标题和描述关联 Issue #12 (Closes #12)

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 2]
- [Task 5] depends on [Task 3, Task 4]
- [Task 6] depends on [Task 5]
- [Task 7] depends on [Task 6]
