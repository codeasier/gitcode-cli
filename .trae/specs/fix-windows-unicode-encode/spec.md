# 修复 Windows GBK 代码页下 UnicodeEncodeError 崩溃 Spec

## Why

在 Windows 默认 GBK 代码页（codepage 936）环境下，当 `gc issue view` 或其他命令输出的内容包含 emoji 等 GBK 无法编码的 Unicode 字符时，`click.echo()` 会抛出 `UnicodeEncodeError` 导致程序崩溃。这是一个影响所有 Windows 中文用户的关键 Bug（Issue #14）。

## What Changes

- 在 CLI 入口 `cli.py` 的 `main()` 函数开头添加 `sys.stdout`/`sys.stderr` 编码安全配置，确保在 Windows GBK 环境下不会因无法编码 Unicode 字符而崩溃
- 新增 `safe_echo()` 工具函数作为 `click.echo()` 的安全封装，对无法编码的字符使用 `errors='replace'` 策略
- 将所有 `click.echo()` 调用替换为 `safe_echo()`，确保 API 返回的用户内容（issue body、PR body、评论等）不会导致编码错误
- 添加针对 Unicode 编码安全的单元测试

## Impact

- Affected specs: 所有命令的输出能力（issue view/list/status、pr view/list/status/diff、auth、formatters）
- Affected code:
  - `src/gitcode_cli/cli.py` — 入口处添加 stdout/stderr 编码配置
  - `src/gitcode_cli/utils.py` — 新增 `safe_echo()` 函数
  - `src/gitcode_cli/commands/issue.py` — 替换 `click.echo` 为 `safe_echo`
  - `src/gitcode_cli/commands/pr.py` — 替换 `click.echo` 为 `safe_echo`
  - `src/gitcode_cli/commands/auth.py` — 替换 `click.echo` 为 `safe_echo`
  - `src/gitcode_cli/formatters.py` — 替换 `click.echo` 为 `safe_echo`
  - `src/gitcode_cli/cli.py` — 替换 `click.echo` 为 `safe_echo`
  - `tests/unit/test_utils.py` — 新增 `safe_echo` 测试
  - `tests/unit/test_formatters.py` — 新增 Unicode 输出测试

## ADDED Requirements

### Requirement: Windows Unicode 编码安全

系统 SHALL 在 Windows GBK 代码页环境下优雅处理 Unicode 输出，不会因 `UnicodeEncodeError` 而崩溃。

#### Scenario: Issue body 包含 emoji 字符
- **WHEN** 用户在 Windows GBK 代码页环境下执行 `gc issue view 42`，且 issue body 包含 emoji 字符（如 📚）
- **THEN** 命令正常输出，emoji 字符被替换为 `?` 而非抛出异常崩溃

#### Scenario: PR body 包含中文和特殊 Unicode 字符
- **WHEN** 用户在 Windows GBK 代码页环境下执行 `gc pr view`，且 PR 内容包含 GBK 无法编码的字符
- **THEN** 命令正常输出，无法编码的字符被替换为 `?`

#### Scenario: 非 Windows 环境不受影响
- **WHEN** 用户在 macOS/Linux 环境下执行任何命令
- **THEN** 输出行为与修改前完全一致，emoji 和 Unicode 字符正常显示

### Requirement: safe_echo 安全输出函数

系统 SHALL 提供 `safe_echo()` 函数作为 `click.echo()` 的安全替代，对无法编码的字符使用 `errors='replace'` 策略。

#### Scenario: 正常 ASCII 文本
- **WHEN** `safe_echo("Hello World")` 被调用
- **THEN** 输出与 `click.echo("Hello World")` 完全一致

#### Scenario: 包含不可编码字符的文本
- **WHEN** `safe_echo("📚 Hello")` 在 GBK 编码的 stdout 上被调用
- **THEN** 输出 `? Hello` 而非抛出 `UnicodeEncodeError`

### Requirement: 入口编码配置

系统 SHALL 在 CLI 入口 `main()` 函数开头尝试将 `sys.stdout` 和 `sys.stderr` 的编码重新配置为 `utf-8`，使用 `errors='replace'` 策略。

#### Scenario: Windows 环境下 stdout 编码重配置
- **WHEN** CLI 在 Windows GBK 环境下启动
- **THEN** `sys.stdout` 和 `sys.stderr` 的编码被重新配置为 `utf-8`（如果支持），或 `safe_echo` 作为 fallback

#### Scenario: 重配置不可用时的 fallback
- **WHEN** `sys.stdout.reconfigure()` 不可用（如某些特殊终端环境）
- **THEN** `safe_echo()` 仍然能安全处理不可编码字符，不会崩溃
