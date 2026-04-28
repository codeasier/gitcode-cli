# 修复 pr create 命令 KeyError: 'html_url' Spec

## Why

`gc pr create` 成功创建 PR 后，如果 API 响应中缺少 `html_url` 字段，`default_formatter` 会因 `data["html_url"]` 硬编码字典键访问而抛出 `KeyError`，导致 CLI 崩溃。PR 实际已创建成功，但用户看不到任何结果，体验极差。

## What Changes

- 修改 `src/gitcode_cli/commands/pr.py` 第 248 行的 `default_formatter`，将 `data["html_url"]` 改为防御性访问，优先使用 `html_url`，回退到 `url`，最终回退到 `Created PR #<number>` 格式
- 新增测试用例：验证 API 响应缺少 `html_url` 时 `pr create` 不崩溃，且输出合理的回退信息
- 在独立 git worktree 中完成修复，使用 `fix/` 前缀分支命名，通过 `gh` 命令提交 PR

## Impact

- Affected code: `src/gitcode_cli/commands/pr.py` (1 行修改)
- Affected tests: `tests/unit/commands/test_pr.py` (新增测试用例)
- 无破坏性变更

## ADDED Requirements

### Requirement: pr create 命令应防御性处理 API 响应中缺失的 html_url

当 `gc pr create` 的 API 响应中缺少 `html_url` 字段时，系统 SHALL 优雅地回退输出，而非崩溃。

#### Scenario: API 响应包含 html_url
- **WHEN** 用户执行 `gc pr create` 且 API 响应包含 `html_url` 字段
- **THEN** 输出 PR 的 `html_url`（与当前行为一致）

#### Scenario: API 响应缺少 html_url 但包含 url
- **WHEN** 用户执行 `gc pr create` 且 API 响应缺少 `html_url` 但包含 `url` 字段
- **THEN** 输出 PR 的 `url` 字段值

#### Scenario: API 响应既缺少 html_url 也缺少 url
- **WHEN** 用户执行 `gc pr create` 且 API 响应既缺少 `html_url` 也缺少 `url`
- **THEN** 输出 `Created PR #<number>` 格式的信息，其中 `<number>` 为 PR 编号

#### Scenario: API 响应缺少所有标识字段
- **WHEN** 用户执行 `gc pr create` 且 API 响应缺少 `html_url`、`url` 和 `number`
- **THEN** 输出 `Created pull request` 作为兜底信息
