# 创建Issue

创建新的 Issue

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-issues

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| repo | string | 是 | 仓库路径(path) |
| title | string | 是 | Issue标题 |
| body | string | 否 | Issue内容 |
| assignee | string | 否 | Issue指派人 |
| milestone | integer | 否 | 里程碑ID |
| labels | string | 否 | 标签,用逗号分隔 |
| security_hole | string | 否 | 是否为安全漏洞 |
| template_path | string | 否 | 模板路径 |
| issue_type | string | 否 | Issue类型 |
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
| issue_state_detail | object | Issue状态详情 |
| issue_type_detail | object | Issue类型详情 |
| issue_priority_detail | object | Issue优先级详情 |
| milestone | object | 里程碑信息 |
| assignee | object | 指派人信息 |
| visibility_reason | string | 可见性原因 |

### 响应示例

```json
{
  "id": 123456,
  "html_url": "https://gitcode.com/owner/repo/issues/1",
  "number": "1",
  "state": "open",
  "title": "Bug: 示例标题",
  "body": "这是一个示例Issue内容",
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
  "updated_at": "2024-01-01T10:00:00+08:00",
  "finished_at": null,
  "labels": [
    {
      "id": 1,
      "name": "bug",
      "color": "ff0000"
    }
  ],
  "issue_state": "open",
  "comments": 0,
  "priority": 1,
  "issue_type": "bug",
  "milestone": null,
  "assignee": null,
  "visibility_reason": "public"
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/issues?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "my-repo",
    "title": "Bug: 发现一个新问题",
    "body": "问题描述...",
    "assignee": "username",
    "labels": "bug,high-priority"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/issues"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "repo": "my-repo",
    "title": "Bug: 发现一个新问题",
    "body": "问题描述...",
    "assignee": "username",
    "labels": "bug,high-priority"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
