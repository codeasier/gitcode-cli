# 修复 API 响应缺少 number 字段导致 KeyError 崩溃 Spec

## Why

`gc pr close` 等命令在 GitCode API 成功执行操作后，因 API 响应 JSON 中缺少 `number` 字段而抛出 `KeyError` 崩溃。用户看到 Python 堆栈跟踪而非成功消息，误以为操作失败。该问题在 Windows 环境下已被实际触发（GitHub Issue #12），但所有平台均存在此风险。

## What Changes

- 将 `commands/pr.py` 和 `commands/issue.py` 中所有 `item['number']` 硬编码访问改为安全的 fallback 链：`item.get('number') or item.get('iid') or <已解析的 number 变量>`
- 在 `utils.py` 中新增辅助函数 `safe_number(item, fallback)` 统一处理 number 字段的安全提取，消除重复代码
- 为所有受影响的命令补充 API 响应缺少 `number` 字段的测试用例
- 在独立 git worktree 中创建修复分支 `fix/issue-12-keyerror-number`，使用 `gh` 命令提交 PR

## Impact

- Affected code:
  - `src/gitcode_cli/commands/pr.py` — 6 处 `item['number']` 访问
  - `src/gitcode_cli/commands/issue.py` — 4 处 `item['number']` 访问
  - `src/gitcode_cli/utils.py` — 新增 `safe_number` 辅助函数
  - `tests/unit/commands/test_pr.py` — 新增测试用例
  - `tests/unit/commands/test_issue.py` — 新增测试用例

## ADDED Requirements

### Requirement: safe_number 辅助函数

系统 SHALL 在 `utils.py` 中提供 `safe_number(item: dict, fallback: int | str) -> int | str` 函数，按优先级从 API 响应中提取 PR/Issue 编号：
1. `item.get('number')` — 首选字段
2. `item.get('iid')` — GitCode/Gitea 备选字段
3. `fallback` — 调用方已解析的 number 参数作为最终兜底

#### Scenario: API 响应包含 number 字段
- **WHEN** `item = {"number": 42, "iid": 1, ...}`
- **THEN** `safe_number(item, 99)` 返回 `42`

#### Scenario: API 响应缺少 number 但有 iid
- **WHEN** `item = {"iid": 1, ...}`（无 number 键）
- **THEN** `safe_number(item, 99)` 返回 `1`

#### Scenario: API 响应既无 number 也无 iid
- **WHEN** `item = {"state": "closed", ...}`（无 number 和 iid）
- **THEN** `safe_number(item, 42)` 返回 `42`（使用 fallback）

## MODIFIED Requirements

### Requirement: pr close 输出成功消息

`pr close` 命令 SHALL 在 PR 成功关闭后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Closed pull request #{item['number']}")`
修改后：`click.echo(f"Closed pull request #{safe_number(item, number)}")`

### Requirement: pr reopen 输出成功消息

`pr reopen` 命令 SHALL 在 PR 成功重新打开后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Reopened pull request #{item['number']}")`
修改后：`click.echo(f"Reopened pull request #{safe_number(item, number)}")`

### Requirement: pr edit 输出成功消息

`pr edit` 命令 SHALL 在 PR 成功编辑后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Edited pull request #{item['number']}")`
修改后：`click.echo(f"Edited pull request #{safe_number(item, number)}")`

### Requirement: pr ready 输出成功消息

`pr ready` 命令 SHALL 在 PR 成功切换状态后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Converted pull request #{item['number']} to draft")` / `click.echo(f"Marked pull request #{item['number']} as ready for review")`
修改后：`click.echo(f"Converted pull request #{safe_number(item, number)} to draft")` / `click.echo(f"Marked pull request #{safe_number(item, number)} as ready for review")`

### Requirement: pr status 列表输出

`pr status` 命令 SHALL 在列出 PR 时安全访问 number 字段。

修改前：`click.echo(f"  #{item['number']}\t{item['state']}\t{item['title']}")`
修改后：`click.echo(f"  #{safe_number(item, '?')}\t{item['state']}\t{item['title']}")`

### Requirement: issue close 输出成功消息

`issue close` 命令 SHALL 在 Issue 成功关闭后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Closed issue #{item['number']}")`
修改后：`click.echo(f"Closed issue #{safe_number(item, number)}")`

### Requirement: issue reopen 输出成功消息

`issue reopen` 命令 SHALL 在 Issue 成功重新打开后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Reopened issue #{item['number']}")`
修改后：`click.echo(f"Reopened issue #{safe_number(item, number)}")`

### Requirement: issue edit 输出成功消息

`issue edit` 命令 SHALL 在 Issue 成功编辑后输出成功消息，且不因 API 响应缺少 `number` 字段而崩溃。

修改前：`click.echo(f"Edited issue #{item['number']}")`
修改后：`click.echo(f"Edited issue #{safe_number(item, number)}")`

### Requirement: issue status 列表输出

`issue status` 命令 SHALL 在列出 Issue 时安全访问 number 字段。

修改前：`click.echo(f"  #{item['number']}\t{item['state']}\t{item['title']}")`
修改后：`click.echo(f"  #{safe_number(item, '?')}\t{item['state']}\t{item['title']}")`
