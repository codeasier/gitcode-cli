# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-06-04

本次发布聚焦于继续补齐 `gc issue` 与 `gc pr` 的 `gh` 兼容行为，完善 PR 查询与评论能力，并修正多处参数解析、输出格式与边界条件问题，让日常命令行使用与脚本集成更加稳定可预期。

### Added

- `pr list` 新增按合并时间筛选能力，便于在较长时间范围内筛选已合并 PR，并补齐 PR 评论行号映射支持，改善 review/comment 相关场景的可用性 ([#128](https://github.com/codeasier/gitcode-cli/pull/128), [#129](https://github.com/codeasier/gitcode-cli/pull/129))

### Fixed

- 修复 `pr list` 搜索状态解析与分页行为，减少带筛选条件时结果异常或翻页不一致的问题 ([#131](https://github.com/codeasier/gitcode-cli/pull/131))
- 修复 `issue` 命令在状态筛选、列表作者解析、查看输出、评论、关闭、重新打开、编辑参数校验与里程碑处理等方面的兼容性缺口，降低与 `gh` 使用习惯不一致带来的困扰 ([#96](https://github.com/codeasier/gitcode-cli/pull/96), [#98](https://github.com/codeasier/gitcode-cli/pull/98), [#102](https://github.com/codeasier/gitcode-cli/pull/102), [#113](https://github.com/codeasier/gitcode-cli/pull/113), [#114](https://github.com/codeasier/gitcode-cli/pull/114), [#115](https://github.com/codeasier/gitcode-cli/pull/115), [#116](https://github.com/codeasier/gitcode-cli/pull/116), [#117](https://github.com/codeasier/gitcode-cli/pull/117), [#118](https://github.com/codeasier/gitcode-cli/pull/118), [#119](https://github.com/codeasier/gitcode-cli/pull/119), [#120](https://github.com/codeasier/gitcode-cli/pull/120), [#121](https://github.com/codeasier/gitcode-cli/pull/121), [#122](https://github.com/codeasier/gitcode-cli/pull/122))
- 修复 `jq` CLI fallback 多项输出解析问题，以及 review 语义、模板和重复 close 近似处理等边界行为，提升脚本化与兼容模式下的稳定性 ([#89](https://github.com/codeasier/gitcode-cli/pull/89), [#91](https://github.com/codeasier/gitcode-cli/pull/91), [#95](https://github.com/codeasier/gitcode-cli/pull/95))

### Changed

- 持续收敛 `gh` 兼容层语义，补充 pending/unsupported 标志的显式反馈，并将部分能力检查前移到命令层，使兼容行为更清晰可维护 ([#88](https://github.com/codeasier/gitcode-cli/pull/88), [#90](https://github.com/codeasier/gitcode-cli/pull/90), [#97](https://github.com/codeasier/gitcode-cli/pull/97))
- 忽略本地生成文件并整理中英文文档结构，减少仓库噪音并提升用户文档可读性 ([#81](https://github.com/codeasier/gitcode-cli/pull/81), [#99](https://github.com/codeasier/gitcode-cli/pull/99), [#100](https://github.com/codeasier/gitcode-cli/pull/100), [#123](https://github.com/codeasier/gitcode-cli/pull/123))

## [0.1.2] - 2026-05-05

本次发布聚焦于提升 `gc` 与 `gh` 的交互兼容性、修复常见命令边界行为，并补齐发布链路自动化，使日常使用与后续发版流程更加稳定顺畅。

### Added

- `help` 输出按 `gh` 风格重新分组与对齐，提升常用命令的可发现性 ([#77](https://github.com/codeasier/gitcode-cli/pull/77))

### Fixed

- 修复 `issue`/`pr` 多个 pending 命令流在 `gh` 兼容场景下的行为不一致问题，降低脚本化调用时的意外结果 ([#73](https://github.com/codeasier/gitcode-cli/pull/73))
- 修复编辑 issue 最后一条评论后接口返回空 payload 时的崩溃问题 ([#75](https://github.com/codeasier/gitcode-cli/pull/75))
- 修复 PR review 评论语义与评论投递方式，减少 review/comment 行为偏差，并补齐 `pr checkout`、`issue close/reopen` 等边界场景处理 ([#61](https://github.com/codeasier/gitcode-cli/pull/61), [#62](https://github.com/codeasier/gitcode-cli/pull/62), [#66](https://github.com/codeasier/gitcode-cli/pull/66), [#55](https://github.com/codeasier/gitcode-cli/pull/55))
- 修复认证、网络与参数冲突等错误场景的退出码和错误反馈，改善命令行可预期性 ([#41](https://github.com/codeasier/gitcode-cli/pull/41), [#42](https://github.com/codeasier/gitcode-cli/pull/42), [#43](https://github.com/codeasier/gitcode-cli/pull/43), [#51](https://github.com/codeasier/gitcode-cli/pull/51))
- 修复 issue 创建、查看、编辑与状态切换相关边界问题，并移除不受支持的 issue 删除功能，避免误导性入口 ([#37](https://github.com/codeasier/gitcode-cli/pull/37), [#38](https://github.com/codeasier/gitcode-cli/pull/38), [#39](https://github.com/codeasier/gitcode-cli/pull/39), [#46](https://github.com/codeasier/gitcode-cli/pull/46), [#50](https://github.com/codeasier/gitcode-cli/pull/50), [#63](https://github.com/codeasier/gitcode-cli/pull/63))
- 修复 `pr create`、`pr close`、`pr merge` 与 rebase merge 错误处理等边界行为，减少非常规输入下的失败方式 ([#45](https://github.com/codeasier/gitcode-cli/pull/45), [#48](https://github.com/codeasier/gitcode-cli/pull/48))

### Changed

- 引入 gh-to-gitcode 适配层并扩展兼容性测试基线，为后续命令语义对齐和回归验证打下基础 ([#59](https://github.com/codeasier/gitcode-cli/pull/59), [#67](https://github.com/codeasier/gitcode-cli/pull/67), [#72](https://github.com/codeasier/gitcode-cli/pull/72))
- 发布流程改为在 PyPI 发布成功后自动创建 GitHub Release，减少手工发版步骤 ([#78](https://github.com/codeasier/gitcode-cli/pull/78))

## [0.1.2a0] - 2026-04-29

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
