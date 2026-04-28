# 获取企业的某个Issue

获取企业中某个 Issue 的详细信息

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issues/:number`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issues-number

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| enterprise | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| number | integer | 是 | issue 全局唯一 id |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

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
| custom_fields | array | 自定义字段列表 |
| visibility_reason | string | 可见性,public:公开可见,confidential:私密,项目成员可见,other:其他原因导致的仅项目成员可见 |

### 响应示例

```json
{
  "id": 123456,
  "html_url": "https://gitcode.com/owner/repo/issues/1",
  "number": "1",
  "state": "open",
  "title": "企业Issue示例",
  "body": "这是企业Issue的详细内容",
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
  "comments": 5,
  "priority": 1,
  "issue_type": "bug",
  "issue_state_detail": {
    "id": 1,
    "name": "开启"
  },
  "issue_type_detail": {
    "id": 1,
    "name": "缺陷"
  },
  "issue_priority_detail": {
    "id": 1,
    "name": "高"
  },
  "custom_fields": [],
  "visibility_reason": "public"
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues/:number?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/my-enterprise/issues/123456"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
