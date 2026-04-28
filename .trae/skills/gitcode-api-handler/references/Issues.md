# Issues API 文档

GitCode Issues API 提供了完整的 Issue 管理功能,包括创建、查询、更新、删除 Issue 及其评论、标签等操作。

## 基本信息

- **API 基础URL**: https://api.gitcode.com/api/v5
- **文档URL**: https://docs.gitcode.com/docs/apis
- **接口总数**: 26 个
- **认证方式**: OAuth2 Token (access_token)

## 接口列表

### Issue 基本操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 1 | 创建Issue | POST | `/repos/:owner/issues` | [create-issue.md](Issues/create-issue.md) |
| 2 | 更新Issue | PATCH | `/repos/:owner/issues/:number` | [update-issue.md](Issues/update-issue.md) |
| 3 | 获取仓库的某个Issue | GET | `/repos/:owner/:repo/issues/:number` | [get-repo-issue.md](Issues/get-repo-issue.md) |
| 4 | 获取仓库所有 issues | GET | `/repos/:owner/:repo/issues` | [get-repo-issues.md](Issues/get-repo-issues.md) |

### Issue 评论操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 5 | 获取仓库某个Issue所有的评论 | GET | `/repos/:owner/:repo/issues/:number/comments` | [get-issue-comments.md](Issues/get-issue-comments.md) |
| 6 | 创建Issue评论 | POST | `/repos/:owner/:repo/issues/:number/comments` | [create-issue-comment.md](Issues/create-issue-comment.md) |
| 7 | 获取仓库所有 Issue 评论 | GET | `/repos/:owner/:repo/issues/comments` | [get-repo-all-comments.md](Issues/get-repo-all-comments.md) |
| 8 | 更新Issue某条评论 | PATCH | `/repos/:owner/:repo/issues/comments/:id` | [update-issue-comment.md](Issues/update-issue-comment.md) |
| 9 | 删除Issue某条评论 | DELETE | `/repos/:owner/:repo/issues/comments/:id` | [delete-issue-comment.md](Issues/delete-issue-comment.md) |
| 10 | 获取仓库Issue某条评论 | GET | `/repos/:owner/:repo/issues/comments/:id` | [get-issue-comment.md](Issues/get-issue-comment.md) |

### Issue 标签操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 11 | 获取企业某个Issue所有标签 | GET | `/enterprises/:enterprise/issues/:issue_id/labels` | [get-enterprise-issue-labels.md](Issues/get-enterprise-issue-labels.md) |
| 12 | 创建Issue标签 | POST | `/repos/:owner/:repo/issues/:number/labels` | [create-issue-labels.md](Issues/create-issue-labels.md) |
| 13 | 删除Issue标签 | DELETE | `/repos/:owner/:repo/issues/:number/labels/:name` | [delete-issue-label.md](Issues/delete-issue-label.md) |

### Issue 关联操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 14 | 获取 issue 关联的 pull requests | GET | `/repos/:owner/:repo/issues/:number/pull_requests` | [get-issue-pull-requests.md](Issues/get-issue-pull-requests.md) |
| 15 | 获取issue关联的分支列表 | GET | `/repos/:owner/:repo/issues/:number/related_branches` | [get-issue-related-branches.md](Issues/get-issue-related-branches.md) |
| 16 | 设置Issue关联的分支 | PUT | `/repos/:owner/:repo/issues/:number/related_branches` | [set-issue-related-branches.md](Issues/set-issue-related-branches.md) |

### Issue 操作日志和历史

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 17 | 获取某个issue下的操作日志 | GET | `/repos/:owner/issues/:number/operate_logs` | [get-issue-operate-logs.md](Issues/get-issue-operate-logs.md) |
| 18 | 获取issue的修改历史 | GET | `/repos/:owner/:repo/issues/:number/modify_history` | [get-issue-modify-history.md](Issues/get-issue-modify-history.md) |
| 19 | 获取issue评论的修改历史 | GET | `/repos/:owner/:repo/issues/comment/:comment_id/modify_history` | [get-comment-modify-history.md](Issues/get-comment-modify-history.md) |

### Issue 表态操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 20 | 获取issue的表态列表 | GET | `/repos/:owner/:repo/issues/:number/user_reactions` | [get-issue-reactions.md](Issues/get-issue-reactions.md) |
| 21 | 获取issue评论的表态列表 | GET | `/repos/:owner/:repo/issues/comment/:comment_id/user_reactions` | [get-comment-reactions.md](Issues/get-comment-reactions.md) |

### 企业和组织 Issue 操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 22 | 获取某个企业的所有Issues | GET | `/enterprises/:enterprise/issues` | [get-enterprise-issues.md](Issues/get-enterprise-issues.md) |
| 23 | 获取企业的某个Issue | GET | `/enterprises/:enterprise/issues/:number` | [get-enterprise-issue.md](Issues/get-enterprise-issue.md) |
| 24 | 获取企业某个Issue所有评论 | GET | `/enterprises/:enterprise/issues/:number/comments` | [get-enterprise-issue-comments.md](Issues/get-enterprise-issue-comments.md) |
| 25 | 获取企业issue状态 | GET | `/enterprises/:enterprise/issue/statuses` | [get-enterprise-issue-statuses.md](Issues/get-enterprise-issue-statuses.md) |
| 26 | 获取当前用户某个组织的Issues | GET | `/orgs/:org/issues` | [get-org-issues.md](Issues/get-org-issues.md) |

### 用户 Issue 操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|---------|------|------|----------|
| 27 | 获取授权用户的所有Issues | GET | `/user/issues` | [get-user-issues.md](Issues/get-user-issues.md) |

## 接口分类

### 按 HTTP 方法分类

- **GET 接口**: 19 个 - 用于查询和获取数据
- **POST 接口**: 3 个 - 用于创建资源
- **PATCH 接口**: 2 个 - 用于更新资源
- **PUT 接口**: 1 个 - 用于设置资源
- **DELETE 接口**: 2 个 - 用于删除资源

### 按功能模块分类

1. **Issue 基本操作** (4个): 创建、更新、查询 Issue
2. **Issue 评论操作** (6个): 评论的增删改查
3. **Issue 标签操作** (3个): 标签管理
4. **Issue 关联操作** (3个): PR 和分支关联
5. **Issue 历史记录** (3个): 操作日志和修改历史
6. **Issue 表态操作** (2个): 点赞等表态功能
7. **企业/组织 Issue** (5个): 企业和组织级别的 Issue 管理
8. **用户 Issue** (1个): 用户个人的 Issue 查询

## 快速开始

### 1. 创建 Issue

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/issues"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "repo": "my-repo",
    "title": "Bug: 发现一个新问题",
    "body": "问题描述...",
}

response = requests.post(url, params=params, json=data)
issue = response.json()
print(f"Created Issue #{issue['number']}: {issue['html_url']}")
```

### 2. 查询仓库 Issues

```python
url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues"
params = {
    "access_token": "YOUR_TOKEN",
    "state": "open",
    "per_page": 20
}

response = requests.get(url, params=params)
issues = response.json()

for issue in issues:
    print(f"#{issue['number']} - {issue['title']}")
```

### 3. 添加评论

```python
url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/comments"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "body": "这是一条评论",
}

response = requests.post(url, params=params, json=data)
comment = response.json()
print(f"Comment ID: {comment['id']}")
```

### 4. 更新 Issue

```python
url = "https://api.gitcode.com/api/v5/repos/owner/issues/1"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "repo": "my-repo",
    "state": "closed",
}

response = requests.patch(url, json=data)
issue = response.json()
print(f"Issue state: {issue['state']}")
```

## 认证说明

所有 Issues API 接口都需要通过 `access_token` 参数进行认证。获取 access_token 的方式:

1. 在 GitCode 创建 OAuth 应用
2. 通过 OAuth 授权流程获取 access_token
3. 在 API 请求中添加 `access_token` 参数

## 分页说明

大多数列表查询接口支持分页,通过以下参数控制:

- `page`: 当前页码,从 1 开始
- `per_page`: 每页数量,最大为 100,默认为 20

## 响应格式

所有接口返回 JSON 格式数据,包含以下通用字段:

- `id`: 资源唯一标识
- `created_at`: 创建时间 (ISO 8601 格式)
- `updated_at`: 更新时间 (ISO 8601 格式)

## 错误处理

API 返回标准 HTTP 状态码:

- `200 OK`: 请求成功
- `201 Created`: 资源创建成功
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未授权或 token 无效
- `403 Forbidden`: 无权限访问
- `404 Not Found`: 资源不存在
- `422 Unprocessable Entity`: 请求格式正确但语义错误

## 最佳实践

1. **使用分页**: 查询大量数据时使用分页,避免一次性获取过多数据
2. **缓存 access_token**: 避免频繁请求授权
3. **错误处理**: 妥善处理 API 错误响应
4. **速率限制**: 注意 API 调用频率限制
5. **数据验证**: 提交前验证必填字段

## 统计信息

- **总接口数**: 26 个
- **详细文档数**: 26 个
- **示例代码**: 每个接口包含 cURL 和 Python 示例
- **响应示例**: 每个接口包含完整的 JSON 响应示例

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis)
- [OAuth 认证文档](https://docs.gitcode.com/docs/oauth)
- [API 最佳实践](https://docs.gitcode.com/docs/best-practices)

## 更新日志

- **2024-01-01**: 初始版本,包含 26 个 Issues API 接口文档
