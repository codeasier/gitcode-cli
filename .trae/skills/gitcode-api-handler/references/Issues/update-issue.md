# 更新Issue

更新指定的 Issue 信息

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/issues/:number`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| repo | string | 是 | 仓库路径(path) |
| title | string | 否 | Issue标题 |
| body | string | 否 | Issue内容 |
| state | string | 否 | Issue状态(open/closed) |
| assignee | string | 否 | Issue指派人 |
| milestone | integer | 否 | 里程碑ID |
| labels | string | 否 | 标签,用逗号分隔 |
| security_hole | string | 否 | 是否为安全漏洞 |
| status | string | 否 | Issue状态 |
| issue_severity | string | 否 | Issue严重程度 |
| custom_fields | array | 否 | 自定义字段列表 |
| custom_fields[].field_name | string | 是 | 字段名称 |
| custom_fields[].field_values | array | 是 | 字段值列表 |

## 响应

### 响应结构

| 字段 | 类型 | 描述 |
|------|------|------|
| id | integer | Issue ID |
| html_url | string | Issue的HTML URL |
| number | string | Issue编号 |
| state | string | Issue状态 |
| title | string | Issue标题 |
| body | string | Issue内容 |
| user | object | 创建者信息 |
| repository | object | 仓库信息 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| finished_at | string | 完成时间 |
| labels | array | 标签列表 |
| issue_state | string | Issue状态 |
| comments | integer | 评论数 |
| priority | integer | 优先级 |
| issue_type | string | Issue类型 |
| milestone | object | 里程碑信息 |
| assignee | object | 指派人信息 |
| visibility_reason | string | 可见性原因 |

### 响应示例

```json
{
  "id": 123456,
  "html_url": "https://gitcode.com/owner/repo/issues/1",
  "number": "1",
  "state": "closed",
  "title": "Bug: 已修复的问题",
  "body": "问题已修复",
  "user": {
    "id": "123",
    "login": "username",
    "name": "用户名"
  },
  "repository": {
    "id": 789,
    "name": "repo",
    "full_name": "owner/repo"
  },
  "created_at": "2024-01-01T10:00:00+08:00",
  "updated_at": "2024-01-02T15:30:00+08:00",
  "finished_at": "2024-01-02T15:30:00+08:00",
  "labels": [],
  "issue_state": "closed",
  "comments": 5,
  "priority": 1,
  "issue_type": "bug",
  "milestone": null,
  "assignee": {
    "id": "456",
    "login": "assignee_user",
    "name": "指派人"
  },
  "visibility_reason": "public"
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/issues/:number?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "my-repo",
    "title": "更新后的标题",
    "state": "closed"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/issues/1"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "repo": "my-repo",
    "title": "更新后的标题",
    "state": "closed"
}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
