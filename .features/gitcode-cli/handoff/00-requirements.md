# Requirements: gitcode-cli

## Problem Statement
- GitCode (gitcode.com) 是一个国内代码托管平台，提供了完整的 REST API (v5)，但缺少官方 CLI 工具
- 开发者习惯使用 `gh` (GitHub CLI) 进行日常操作，需要一个命令风格对齐 `gh` 的 GitCode CLI 工具
- 当前操作 GitCode 仓库必须通过 Web UI 或手动构造 API 请求，效率低下

## Goals
- 实现一个 Python CLI 工具，命令名为 `gc`（对标 GitHub CLI 的 `gh`），尽可能完全对标 GitHub CLI 的命令结构和参数
- 优先覆盖 Issue、PR、评论/检视意见相关能力
- 项目采用 src-layout，可通过 `pip install` 安装
- 支持通过环境变量 `GC_TOKEN`（对标 GitHub 的 `GH_TOKEN` 命名风格）或配置文件管理 access_token 认证
- 从用户执行 `gc` 命令时所在目录的 git remote 自动推断 owner/repo

## Non-Goals
- 不实现 Repository CRUD 管理（创建、删除、Fork 等）
- 不实现 Release/Tag/Branch 管理（可后续扩展）
- 不实现 OAuth 授权流程（仅支持 personal access token）
- 不实现 GitHub Actions / CI/CD 等能力
- 不实现 SSH key 管理
- 不做 Web UI 或 TUI 界面

## Users / Primary Scenarios
- **Primary user**: 使用 GitCode 托管代码的开发者，熟悉 `gh` CLI 的使用习惯
- **Core scenario 1**: Issue 管理 — 列出、查看、创建、更新、关闭 Issue，添加评论
- **Core scenario 2**: PR 管理 — 列出、查看、创建、更新、合并 PR，添加评论/检视意见
- **Core scenario 3**: 代码评审 — 在 PR 上添加代码行评论、处理审查通过

## Constraints

### Technical constraints
- Python 3.9+，使用 `click` 作为 CLI 框架
- 使用 `httpx` 作为 HTTP 客户端
- API 基础 URL: `https://api.gitcode.com/api/v5`
- 认证方式: access_token (查询参数或 Header)
- 分页: page/per_page，最大 100，默认 20

### GitCode API 与 gh 对齐约束（关键差异）

#### Issue API 差异
1. **创建 Issue 路径差异**: GitCode 为 `POST /repos/:owner/issues`（body 中传 `repo` 字段），gh 为 `POST /repos/:owner/:repo/issues`（path 中传 repo）
2. **更新 Issue 路径差异**: GitCode 为 `PATCH /repos/:owner/issues/:number`（body 中传 `repo` 字段），无 repo 在 path 中
3. **Issue number 为 string 类型**: GitCode 的 issue number 是字符串，gh 是整数
4. **Issue 状态差异**: GitCode 支持 `open/closed/all`（list 时），以及 `progressing/rejected`（user issues 时）；gh 仅支持 `open/closed`
5. **GitCode 特有字段**: `issue_type`, `issue_severity`, `security_hole`, `custom_fields`, `issue_state_detail`, `issue_type_detail` — 这些在 gh 中不存在
6. **标签参数格式**: GitCode 的 labels 是逗号分隔字符串，gh 也是

#### PR API 差异
1. **PR 状态多一个 `merged`**: GitCode 的 PR state 支持 `open/closed/merged/all`，gh 仅 `open/closed/merged`（但 merged 是 gh 支持的）
2. **GitCode PR 特有概念**:
   - **测试人 (testers)**: GitCode 有独立的测试人管理，gh 没有
   - **审查人 (assignees)**: GitCode 的 assignees 指的是审查人，与 gh 的 assignees（指派人）含义不同
   - **评审人 (reviewers)**: 与 gh 的 reviewers 概念接近
   - **handle-pr-review**: GitCode 的审查通过是一个独立 API，gh 通过 `gh pr review --approve`
   - **handle-pr-test**: GitCode 的测试通过是一个独立 API，gh 没有此概念
3. **PR 评论类型**: GitCode 区分 `diff_comment`（代码行评论）和 `pr_comment`（普通评论），gh 统一为 review comment
4. **PR 评论参数差异**: GitCode 使用 `path` + `position` 定位代码行评论，gh 使用 `path` + `line` + `side` + `commit_id`
5. **合并方法**: GitCode 使用 `merge_method` (merge/squash/rebase)，gh 使用 `--merge`/`--squash`/`--rebase` flags
6. **PR 关联 Issue**: GitCode 有独立的 link/unlink issue API，gh 通过 PR body 中的关键字自动关联

### CLI 对齐策略
- **命令名**: `gc`（对标 `gh`），如 `gc issue list`, `gc pr create`
- **完全对标 gh CLI**: 命令结构、子命令名称、参数名称、参数行为尽可能 100% 对齐 `gh`
- 参数名对齐: `--title`, `--body`, `--assignee`, `--label`, `--state`, `--repo`, `--web` 等
- GitCode 特有能力通过额外参数暴露: `--tester`, `--issue-type`, `--severity` 等
- 无法对齐的命令/参数通过帮助文档说明差异

### Timeline constraints
- 第一阶段: Issue CRUD + 评论、PR CRUD + 评论/检视意见、认证配置

### Compatibility constraints
- 支持 macOS / Linux
- Python 3.9+

## Acceptance Summary
- 用户可以 `pip install .` 安装后获得 `gc` 命令
- `gc auth login` 可以配置 access_token
- `gc issue list/view/create/close/comment` 可以管理 Issue
- `gc pr list/view/create/close/merge/comment/review` 可以管理 PR
- 支持 `GC_TOKEN` 环境变量（对标 `GH_TOKEN` 命名风格）
- 自动从当前目录 git remote 推断 owner/repo，也支持 `-R owner/repo` 手动指定（对标 `gh -R`）
- 输出格式清晰，支持 `--json` 输出
- 帮助信息完整，`gc --help` 可以看到所有参数说明

## Open Questions
- ~~是否需要从当前 git remote 自动推断 owner/repo？~~ **已确认: 是，从用户执行 gc 时所在目录推断**
- ~~是否需要支持环境变量？~~ **已确认: 是，使用 `GC_TOKEN`（对标 `GH_TOKEN` 命名风格）**

---
Handoff-Meta:
  stage: requirements_clarification
  file: handoff/00-requirements.md
  ready_for_next_stage: true
  last_updated: 2026-04-23T00:00:00+08:00
