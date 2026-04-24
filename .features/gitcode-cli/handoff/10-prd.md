# Product Requirements Document: gc CLI for GitCode

## Executive Summary

### Problem Statement
GitCode 提供了较完整的 REST API，但缺少一个面向开发者日常工作的官方 CLI 工具。当前用户需要在 Web UI 中完成 Issue、Pull Request、评论和检视意见等操作，或者手动拼装 API 请求，导致效率低、自动化能力弱、使用体验与 GitHub CLI (`gh`) 存在明显差距。对于已经熟悉 `gh` 的开发者来说，切换到 GitCode 时缺少一致的命令模型与参数语义，会增加学习成本和操作摩擦。

### Proposed Solution
实现一个基于 Python 的 GitCode CLI 工具，命令名为 `gc`，在命令结构、子命令命名、参数风格和使用体验上尽可能完全对标 GitHub CLI `gh`。第一阶段优先支持 Issue、Pull Request、添加评论/检视意见相关能力，并支持从用户当前所在目录的 git remote 自动推断仓库归属，同时提供 `-R/--repo` 显式指定仓库。工具采用 src-layout 组织，可通过 `pip install .` 安装，并支持与 `GH_TOKEN` 风格一致的 `GC_TOKEN` 环境变量进行认证。

### Success Criteria
- 用户安装后可直接使用 `gc --help`、`gc issue --help`、`gc pr --help` 获取完整帮助信息。
- 第一阶段核心命令可用：`gc issue list/view/create/close/comment` 与 `gc pr list/view/create/close/merge/comment/review`。
- 对于 GitCode API 无法与 `gh` 完全对齐的能力，CLI 能在帮助文本或错误提示中明确说明差异。
- 在处于 Git 仓库目录时，默认命令无需重复输入 owner/repo，能够自动从 remote 推断目标仓库。
- 支持 `GC_TOKEN` 环境变量认证，并允许通过本地配置保存 token。

## User Stories
1. 作为熟悉 `gh` 的开发者，我希望使用 `gc issue list`、`gc pr view` 这类熟悉的命令结构，以便无缝迁移到 GitCode。
2. 作为仓库维护者，我希望在终端中创建和管理 Issue/PR，而不必切换到网页，以便提升工作效率。
3. 作为代码评审者，我希望通过 CLI 直接提交 PR 评论、代码行评论和审查动作，以便将评审流程脚本化。
4. 作为自动化脚本编写者，我希望 CLI 支持 `--json` 输出和稳定的退出码，以便将其集成到 shell 脚本中。
5. 作为在仓库目录中工作的用户，我希望 CLI 自动识别当前 remote 对应的 owner/repo，以便减少重复输入。

## Functional Requirements
- CLI 可执行文件名必须为 `gc`。
- 工具必须采用 Python src-layout，可通过 `pip install .` 安装后暴露控制台命令。
- 提供顶层命令分组，至少包括：`auth`、`issue`、`pr`。
- 支持 `-R, --repo [HOST/]OWNER/REPO` 风格参数，优先对齐 `gh` 的仓库选择方式。
- 当未显式提供 `--repo` 时，应从当前工作目录的 git remote 推断 GitCode 仓库 owner/repo。
- 认证应支持：
  - 环境变量 `GC_TOKEN`
  - 本地配置文件中的 token
- `gc auth login` 应支持写入本地配置，供后续命令复用。

### Issue 功能
- `gc issue list`
  - 支持列出仓库 issues
  - 支持按状态、标签、作者、指派人、搜索词、分页等过滤
  - 支持表格输出和 `--json`
- `gc issue view <number>`
  - 支持查看单个 issue 详情
  - 可选显示评论
- `gc issue create`
  - 支持通过参数传入 title、body、assignee、labels
  - 支持 GitCode 特有字段扩展，如 issue type、severity
- `gc issue close <number>`
  - 通过更新 issue 状态实现关闭
- `gc issue comment <number>`
  - 支持向 issue 添加评论

### Pull Request 功能
- `gc pr list`
  - 支持按状态、base、author、label、搜索词、分页筛选
  - 支持表格输出和 `--json`
- `gc pr view <number>`
  - 支持查看 PR 详情
  - 可选显示评论、文件列表
- `gc pr create`
  - 支持 title、body、head、base、draft、label、assignee、reviewer 等常见参数
  - 对 GitCode 特有字段如 testers 进行扩展暴露
- `gc pr close <number>`
  - 通过更新 PR 状态为 closed 实现关闭
- `gc pr merge <number>`
  - 支持 merge/squash/rebase 三种合并方式
- `gc pr comment <number>`
  - 支持普通评论
  - 支持基于文件路径和位置的代码行评论
- `gc pr review <number>`
  - 提供尽可能接近 `gh pr review` 的用法
  - 至少支持 approve 场景
  - 对 GitCode review API 能力不足或语义不同之处需明确提示

### 对齐与差异说明
- CLI 需要尽量遵循 `gh` 的命令风格，但必须在以下方面显式处理差异：
  - GitCode Issue create/update API 路径与 GitHub 不同，需要在内部兼容处理
  - GitCode 的 PR assignees/testers/reviewers 语义与 GitHub 不完全一致
  - GitCode PR 代码评论使用 `position` 而非 GitHub 的 `line/side/commit` 模型
  - GitCode 存在额外字段和动作，不能强行伪装为 GitHub 完全一致行为
- 任何无法完整对齐的参数或行为，必须在 help 文案或错误提示中说明“为何无法对齐”和“关键差异是什么”。

## Non-Functional Requirements
- **Performance**
  - 普通查询命令应在单次 API 请求范围内快速完成。
  - 分页默认值应控制在合理范围，避免默认拉取过大结果集。
- **Reliability**
  - 对 GitCode API 错误响应提供稳定、可理解的错误输出。
  - 对仓库推断失败、token 缺失、参数不足等情况提供明确提示。
- **Security**
  - 不在命令输出中泄露 token。
  - 优先从环境变量或本地配置安全读取 token，不将 token 写入 shell 历史。
- **Compatibility**
  - 支持 macOS / Linux。
  - 支持 Python 3.9+。
  - 可通过 pip 安装。
- **Usability**
  - 帮助信息、参数名、子命令命名尽量与 `gh` 一致。
  - 默认输出适合人读，`--json` 输出适合机器处理。

## Technical Specifications
- **Major modules**
  - CLI entrypoint：顶层 click command group 与子命令注册
  - Config/Auth：token 读取、配置文件管理、优先级解析
  - Repo Resolver：从当前 git remote 解析 GitCode owner/repo
  - HTTP Client：封装 GitCode API 请求、认证、错误处理
  - Issue Service：Issue/评论相关 API 封装
  - PR Service：PR/评论/review/merge 相关 API 封装
  - Output Formatter：表格、文本、JSON 输出
- **External integrations**
  - GitCode REST API v5: `https://api.gitcode.com/api/v5`
  - 本地 git 命令：用于读取 remote URL 并推断仓库
- **Data / API notes**
  - Issue create/update 需走 `/repos/:owner/issues` 和 `/repos/:owner/issues/:number`，repo 放在请求体中
  - PR review approve 需映射到 GitCode `POST /repos/:owner/:repo/pulls/:number/review`
  - PR comment 同时支持普通评论和 diff 评论，底层使用 `body/path/position`
  - 列表接口统一支持 page/per_page
  - 认证优先级建议：命令参数 > 环境变量 `GC_TOKEN` > 本地配置

## Risks
- **GitCode API 与 gh 语义不一致** -> 通过命令适配层和清晰文档降低认知落差
- **当前目录 remote 解析存在多种 URL 形式** -> 支持 HTTPS/SSH 多种模式解析，并在失败时提示使用 `-R`
- **部分 gh 参数无法映射到 GitCode API** -> 保持参数子集兼容，显式报告不支持项及原因
- **GitCode API 文档与真实行为可能存在偏差** -> 为 client 层设计可观测错误信息，并优先实现文档确认过的核心路径
- **PR review/comment 行定位模型差异大** -> 第一阶段优先支持 GitCode 已提供的 `path + position` 模型，并在帮助中说明与 gh 的差异

## Acceptance Criteria
- [ ] 项目采用 src-layout，安装后暴露 `gc` 命令。
- [ ] `gc --help`、`gc issue --help`、`gc pr --help` 输出完整可用。
- [ ] 支持 `GC_TOKEN` 环境变量认证。
- [ ] 支持从当前 git 仓库 remote 自动推断 owner/repo。
- [ ] 支持 `-R/--repo` 显式指定仓库。
- [ ] `gc issue list/view/create/close/comment` 可调用对应 GitCode API。
- [ ] `gc pr list/view/create/close/merge/comment/review` 可调用对应 GitCode API。
- [ ] 支持 `--json` 输出至少覆盖第一阶段核心读操作。
- [ ] 对无法与 `gh` 完全对齐的行为提供明确说明。
- [ ] 错误提示能够区分认证失败、仓库推断失败、参数错误和 API 失败。

---
Handoff-Meta:
  stage: prd_creation
  file: handoff/10-prd.md
  ready_for_next_stage: true
  last_updated: 2026-04-23T00:10:00+08:00
