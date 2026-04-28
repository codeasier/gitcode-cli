# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-28

### Added

- `auth` 命令组新增 `logout`/`status`/`token` 子命令 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `issue create --label` 改为可重复参数（`multiple=True`） ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `issue close` 新增 `--comment` 和 `--reason` 选项 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `issue edit` 新增 `--body-file`/`--milestone`/`--remove-milestone` 选项 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `pr view` 新增 `--comments` 标志 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `pr comment` 新增 `--body-file`/`--editor`/`--web` 选项 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `pr merge` 新增 `--delete-branch` 选项 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `pr edit` 新增 `--body-file`/`--milestone`/`--remove-milestone` 选项 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))
- `PullRequestService` 新增 `list_comments()` 方法 ([#10](https://github.com/codeasier/gitcode-cli/issues/10))

### Fixed

- 修复 API 响应缺少 `number` 字段时 `pr close`/`issue close` 崩溃的问题 ([#12](https://github.com/codeasier/gitcode-cli/issues/12), [#15](https://github.com/codeasier/gitcode-cli/pull/15))
- 修复 `pr create` 响应缺少 `html_url` 字段时崩溃的问题 ([#13](https://github.com/codeasier/gitcode-cli/issues/13), [#18](https://github.com/codeasier/gitcode-cli/pull/18))
- 修复 Windows GBK 代码页下 Unicode 输出崩溃的问题，新增 `safe_echo()` 工具函数和 `_configure_stdout_encoding()` 自动配置 ([#14](https://github.com/codeasier/gitcode-cli/issues/14), [#16](https://github.com/codeasier/gitcode-cli/pull/16))

### Changed

- `safe_number()` 改用显式键存在性检查，避免 falsy 值陷阱（如 `number=0`）

## [0.1.0] - 2025-04-28

### Added

- Add `gitcode` as an alternative console script entry point to resolve PowerShell `gc` alias conflict with `Get-Content` ([#1](https://github.com/codeasier/gitcode-cli/issues/1))
- Add "Windows PowerShell Users" troubleshooting section in README
