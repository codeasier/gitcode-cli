# 修改项目代码审查设置

修改项目的代码审查相关设置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/reviewer`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-reviewer

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

### 请求体参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| reviewer_enabled | boolean | 否 | 是否启用代码审查 |
| required_reviewers | integer | 否 | 必需的审查者数量 |
| auto_assign_reviewers | boolean | 否 | 是否自动分配审查者 |
| reviewer_usernames | array | 否 | 审查者用户名列表 |
| require_code_owner_review | boolean | 否 | 是否要求代码所有者审查 |
| dismiss_stale_reviews | boolean | 否 | 新提交时是否清除旧的审查批准 |
| require_last_push_approval | boolean | 否 | 是否要求最后一次推送的批准 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| enabled | boolean | 是否启用代码审查 |
| required_reviewers | integer | 必需的审查者数量 |
| auto_assign | boolean | 是否自动分配审查者 |
| reviewers | array | 审查者列表 |
| require_code_owner_review | boolean | 是否要求代码所有者审查 |
| dismiss_stale_reviews | boolean | 新提交时是否清除旧的审查批准 |
| require_last_push_approval | boolean | 是否要求最后一次推送的批准 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/reviewer?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_enabled": true,
    "required_reviewers": 2,
    "auto_assign_reviewers": true,
    "reviewer_usernames": ["user1", "user2", "user3"],
    "require_code_owner_review": true,
    "dismiss_stale_reviews": true
  }'
```

## 响应示例

```json
{
  "enabled": true,
  "required_reviewers": 2,
  "auto_assign": true,
  "reviewers": [
    {
      "id": 1,
      "username": "user1",
      "name": "用户1"
    },
    {
      "id": 2,
      "username": "user2",
      "name": "用户2"
    },
    {
      "id": 3,
      "username": "user3",
      "name": "用户3"
    }
  ],
  "require_code_owner_review": true,
  "dismiss_stale_reviews": true,
  "require_last_push_approval": false,
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [获取 Pull Request设置](get-pull-request-settings.md)
- [更新 Pull Request设置](update-pull-request-settings.md)
