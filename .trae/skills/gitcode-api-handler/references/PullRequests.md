# Pull Requests API 文档

GitCode Pull Requests API 提供了对 Pull Request 的完整操作能力，包括创建、查询、合并、评论、标签管理等功能。

## 基本信息

- **文档URL**: https://docs.gitcode.com/docs/apis/pull-requests
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 44个

## 接口列表

### Pull Request 基本操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 获取项目Pull Request列表 | GET | `/repos/:owner/:repo/pulls` | [查看详情](./PullRequests/get-pull-requests-list.md) |
| 2 | 创建Pull Request | POST | `/repos/:owner/:repo/pulls` | [查看详情](./PullRequests/create-pull-request.md) |
| 3 | 获取单个Pull Request | GET | `/repos/:owner/:repo/pulls/:number` | [查看详情](./PullRequests/get-single-pull-request.md) |
| 4 | 更新Pull Request信息 | PATCH | `/repos/:owner/:repo/pulls/:number` | [查看详情](./PullRequests/update-pull-request.md) |
| 5 | 合并Pull Request | PUT | `/repos/:owner/:repo/pulls/:number/merge` | [查看详情](./PullRequests/merge-pull-request.md) |
| 6 | 判断Pull Request是否合并 | GET | `/repos/:owner/:repo/pulls/:number/merge` | [查看详情](./PullRequests/check-pull-request-merged.md) |

### Pull Request 评论管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 7 | 提交pull request 评论 | POST | `/repos/:owner/:repo/pulls/:number/comments` | [查看详情](./PullRequests/create-pr-comment.md) |
| 8 | 获取某个Pull Request的所有评论 | GET | `/repos/:owner/:repo/pulls/:number/comments` | [查看详情](./PullRequests/get-pr-comments.md) |
| 9 | 获取Pull Request某条评论 | GET | `/repos/:owner/:repo/pulls/comments/:id` | [查看详情](./PullRequests/get-pr-comment.md) |
| 10 | 编辑评论 | PATCH | `/repos/:owner/:repo/pulls/comments/:id` | [查看详情](./PullRequests/update-pr-comment.md) |
| 11 | 删除评论 | DELETE | `/repos/:owner/:repo/pulls/comments/:id` | [查看详情](./PullRequests/delete-pr-comment.md) |
| 12 | 回复Pull Request评论 | POST | `/repos/:owner/:repo/pulls/:number/discussions/:discussion_id/comments` | [查看详情](./PullRequests/reply-pr-comment.md) |
| 13 | 修改检视意见解决状态 | PUT | `/repos/:owner/:repo/pulls/:number/comments/:discussion_id` | [查看详情](./PullRequests/update-discussion-resolved-status.md) |

### Pull Request 文件与提交

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 14 | Pull Request Commit文件列表 | GET | `/repos/:owner/:repo/pulls/:number/files` | [查看详情](./PullRequests/get-pr-files.md) |
| 15 | pr提交的文件变更信息 | GET | `/repos/:owner/:repo/pulls/:number/files.json` | [查看详情](./PullRequests/get-pr-files-json.md) |
| 16 | 获取某Pull Request的所有Commit信息 | GET | `/repos/:owner/:repo/pulls/:number/commits` | [查看详情](./PullRequests/get-pr-commits.md) |
| 17 | 获取文件内容 | GET | `/:owner/:repo/raw/:head_sha/:name` | [查看详情](./PullRequests/get-file-content.md) |

### Pull Request 标签管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 18 | 创建 Pull Request标签 | POST | `/repos/:owner/:repo/pulls/:number/labels` | [查看详情](./PullRequests/create-pr-labels.md) |
| 19 | 获取某个 Pull Request的所有标签 | GET | `/repos/:owner/:repo/pulls/:number/labels` | [查看详情](./PullRequests/get-pr-labels.md) |
| 20 | 替换 Pull Request所有标签 | PUT | `/repos/:owner/:repo/pulls/:number/labels` | [查看详情](./PullRequests/replace-pr-labels.md) |
| 21 | 删除 Pull Request标签 | DELETE | `/repos/:owner/:repo/pulls/:number/labels/:name` | [查看详情](./PullRequests/delete-pr-label.md) |

### Pull Request Issue 关联

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 22 | 获取pr关联的issue | GET | `/repos/:owner/:repo/pulls/:number/issues` | [查看详情](./PullRequests/get-pr-linked-issues.md) |
| 23 | Pull Request关联issue | POST | `/repos/:owner/:repo/pulls/:number/issues` | [查看详情](./PullRequests/link-pr-issues.md) |
| 24 | Pull Request删除关联的issue | DELETE | `/repos/:owner/:repo/pulls/:number/issues` | [查看详情](./PullRequests/unlink-pr-issues.md) |

### Pull Request 测试与审查

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 25 | 处理 Pull Request测试 | POST | `/repos/:owner/:repo/pulls/:number/test` | [查看详情](./PullRequests/handle-pr-test.md) |
| 26 | 处理 Pull Request审查 | POST | `/repos/:owner/:repo/pulls/:number/review` | [查看详情](./PullRequests/handle-pr-review.md) |
| 27 | 获取某个Pull Request的操作日志 | GET | `/repos/:owner/:repo/pulls/:number/operate_logs` | [查看详情](./PullRequests/get-pr-operate-logs.md) |

### Pull Request 测试人管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 28 | 重置 Pull Request测试 的状态 | PATCH | `/repos/:owner/:repo/pulls/:number/testers` | [查看详情](./PullRequests/reset-pr-testers-status.md) |
| 29 | 指派用户测试 Pull Request | POST | `/repos/:owner/:repo/pulls/:number/testers` | [查看详情](./PullRequests/assign-pr-testers.md) |
| 30 | 取消用户测试Pull Request | DELETE | `/repos/:owner/:repo/pulls/:number/testers` | [查看详情](./PullRequests/remove-pr-testers.md) |
| 31 | 获取可作为Pull Request测试人列表 | GET | `/repos/:owner/:repo/pulls/option_testers` | [查看详情](./PullRequests/get-pr-testers-list.md) |

### Pull Request 审查人管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 32 | 重置 Pull Request审查 的状态 | PATCH | `/repos/:owner/:repo/pulls/:number/assignees` | [查看详情](./PullRequests/reset-pr-assignees-status.md) |
| 33 | 指派用户审查 Pull Request | POST | `/repos/:owner/:repo/pulls/:number/assignees` | [查看详情](./PullRequests/assign-pr-assignees.md) |
| 34 | 取消用户审查 Pull Request | DELETE | `/repos/:owner/:repo/pulls/:number/assignees` | [查看详情](./PullRequests/remove-pr-assignees.md) |

### Pull Request 评审人管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 35 | 指派用户评审Pull Request | POST | `/repos/:owner/:repo/pulls/:number/reviewers` | [查看详情](./PullRequests/assign-pr-reviewers.md) |
| 36 | 取消用户评审Pull Request | DELETE | `/repos/:owner/:repo/pulls/:number/reviewers` | [查看详情](./PullRequests/remove-pr-reviewers.md) |
| 37 | 获取可作为Pull Request评审人列表 | GET | `/repos/:owner/:repo/pulls/:number/option_reviewers` | [查看详情](./PullRequests/get-pr-reviewers-list.md) |

### Pull Request 表态与历史

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 38 | 获取Pull Request的表态列表 | GET | `/repos/:owner/:repo/pulls/:number/user_reactions` | [查看详情](./PullRequests/get-pr-reactions.md) |
| 39 | 获取Pull Request评论的表态列表 | GET | `/repos/:owner/:repo/pulls/comment/:comment_id/user_reactions` | [查看详情](./PullRequests/get-pr-comment-reactions.md) |
| 40 | 获取Pull Request的修改历史 | GET | `/repos/:owner/:repo/pulls/:number/modify_history` | [查看详情](./PullRequests/get-pr-modify-history.md) |
| 41 | 获取Pull Request评论的修改历史 | GET | `/repos/:owner/:repo/pulls/comment/:comment_id/modify_history` | [查看详情](./PullRequests/get-pr-comment-modify-history.md) |

### 企业与组织 Pull Request

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 42 | 企业 Pull Request列表 | GET | `/enterprises/:enterprise/pull_requests` | [查看详情](./PullRequests/get-enterprise-pull-requests.md) |
| 43 | 组织 Pull Request列表 | GET | `/orgs/:org/pull_requests` | [查看详情](./PullRequests/get-org-pull-requests.md) |
| 44 | 获取企业 issue 关联的 Pull Requests | GET | `/enterprises/:enterprise/issues/:number/pull_requests` | [查看详情](./PullRequests/get-enterprise-issue-pull-requests.md) |

## 接口概览

### Pull Request 基本操作

#### 获取项目Pull Request列表
获取指定仓库的所有 Pull Request 列表，支持按状态、排序、时间等条件筛选。

#### 创建Pull Request
创建一个新的 Pull Request，需要指定源分支、目标分支和标题。

#### 合并Pull Request
合并指定的 Pull Request，支持选择合并方式（merge/squash/rebase）。

### 评论管理

Pull Request 支持多种类型的评论：
- 普通评论（PR评论）
- 代码行评论（Diff评论）
- 讨论回复

### 测试与审查

Pull Request 提供完整的测试和审查流程：
- 测试人管理：指派、取消测试人员
- 审查人管理：指派、取消审查人员
- 评审人管理：指派、取消评审人员

### 标签与关联

- 支持为 Pull Request 添加、删除、替换标签
- 支持关联和取消关联 Issue

## 统计信息

| 分类 | 接口数量 |
|------|----------|
| Pull Request 基本操作 | 6 |
| 评论管理 | 7 |
| 文件与提交 | 4 |
| 标签管理 | 4 |
| Issue 关联 | 3 |
| 测试与审查 | 3 |
| 测试人管理 | 4 |
| 审查人管理 | 3 |
| 评审人管理 | 3 |
| 表态与历史 | 4 |
| 企业与组织 | 3 |
| **总计** | **44** |

## 参考链接

- [GitCode API 文档](https://docs.gitcode.com/docs/apis)
- [GitCode 官网](https://gitcode.com)
