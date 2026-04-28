# 获取仓库动态

获取指定仓库的动态事件列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/events`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-events

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 页码,默认为1 |
| per_page | integer | 否 | 每页数量,默认为30,最大为100 |

## 响应字段

返回事件数组,每个元素包含事件的详细信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 事件ID |
| type | string | 事件类型 |
| actor | object | 事件触发者信息 |
| └─ id | integer | 用户ID |
| └─ login | string | 用户名 |
| └─ display_login | string | 显示名称 |
| └─ avatar_url | string | 头像URL |
| └─ url | string | 用户URL |
| repo | object | 仓库信息 |
| └─ id | integer | 仓库ID |
| └─ name | string | 仓库名称 |
| └─ url | string | 仓库URL |
| payload | object | 事件负载,根据事件类型不同而不同 |
| public | boolean | 是否公开 |
| created_at | string | 事件创建时间,ISO 8601格式 |
| org | object | 组织信息(如果适用) |

### 常见事件类型

- **PushEvent**: 推送代码事件
- **IssuesEvent**: Issue相关事件
- **IssueCommentEvent**: Issue评论事件
- **PullRequestEvent**: Pull Request相关事件
- **PullRequestReviewEvent**: Pull Request审查事件
- **PullRequestReviewCommentEvent**: Pull Request评论事件
- **WatchEvent**: Star仓库事件
- **ForkEvent**: Fork仓库事件
- **CreateEvent**: 创建分支或标签事件
- **DeleteEvent**: 删除分支或标签事件
- **ReleaseEvent**: 发布版本事件

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/events?access_token=YOUR_TOKEN&page=1&per_page=30"
```

## 响应示例

```json
[
  {
    "id": "1234567890",
    "type": "PushEvent",
    "actor": {
      "id": 12345,
      "login": "johndoe",
      "display_login": "John Doe",
      "avatar_url": "https://gitcode.com/avatars/johndoe",
      "url": "https://api.gitcode.com/api/v5/users/johndoe"
    },
    "repo": {
      "id": 67890,
      "name": "owner/repo",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo"
    },
    "payload": {
      "push_id": 1234567890,
      "size": 1,
      "distinct_size": 1,
      "ref": "refs/heads/master",
      "head": "abc123def456abc123def456abc123def456abc1",
      "before": "def456abc123def456abc123def456abc123def4",
      "commits": [
        {
          "sha": "abc123def456abc123def456abc123def456abc1",
          "author": {
            "name": "John Doe",
            "email": "john@example.com"
          },
          "message": "Add new feature",
          "distinct": true,
          "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/abc123"
        }
      ]
    },
    "public": true,
    "created_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": "1234567891",
    "type": "IssuesEvent",
    "actor": {
      "id": 12345,
      "login": "johndoe",
      "display_login": "John Doe",
      "avatar_url": "https://gitcode.com/avatars/johndoe",
      "url": "https://api.gitcode.com/api/v5/users/johndoe"
    },
    "repo": {
      "id": 67890,
      "name": "owner/repo",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo"
    },
    "payload": {
      "action": "opened",
      "issue": {
        "id": 98765,
        "number": 42,
        "title": "Bug report",
        "body": "Description of the bug",
        "state": "open",
        "user": {
          "id": 12345,
          "login": "johndoe"
        },
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      }
    },
    "public": true,
    "created_at": "2024-01-15T10:00:00Z"
  },
  {
    "id": "1234567892",
    "type": "PullRequestEvent",
    "actor": {
      "id": 12345,
      "login": "johndoe",
      "display_login": "John Doe",
      "avatar_url": "https://gitcode.com/avatars/johndoe",
      "url": "https://api.gitcode.com/api/v5/users/johndoe"
    },
    "repo": {
      "id": 67890,
      "name": "owner/repo",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo"
    },
    "payload": {
      "action": "opened",
      "number": 15,
      "pull_request": {
        "id": 54321,
        "number": 15,
        "title": "Add new feature",
        "body": "Description of the feature",
        "state": "open",
        "user": {
          "id": 12345,
          "login": "johndoe"
        },
        "created_at": "2024-01-15T09:30:00Z",
        "updated_at": "2024-01-15T09:30:00Z"
      }
    },
    "public": true,
    "created_at": "2024-01-15T09:30:00Z"
  }
]
```

## 相关接口

- [获取仓库贡献者](get-contributors.md)
- [获取仓库贡献者统计信息](get-contributors-statistic.md)
- [获取仓库的语言](get-languages.md)
