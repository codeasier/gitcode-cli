# 组织 Pull Request列表

组织 Pull Request列表

## 基本信息

- **方法**: GET
- **路径**: `/orgs/:org/pull_requests`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-org-org-pull-requests

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| org | string | 是 | 组织的路径(path/login) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| state | string | 否 | Pull Request状态，all：所有，open：开启，closed：关闭，merged：合并 |
| sort | string | 否 | 排序字段，创建时间：created，更新时间：updated。默认按创建时间 |
| direction | string | 否 | 升序：asc，降序：desc |
| page | integer | 否 | 当前的页码:默认为 1 |
| per_page | string | 否 | 每页数量:默认20 |
| base | string | 否 | 目标分支 |
| author | string | 否 | pull request作者 |
| search | string | 否 | 根据 title、description 模糊查询 |
| created_after | string | 否 | 返回在指定时间之后创建的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| created_before | string | 否 | 返回在指定时间之前创建的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| updated_before | string | 否 | 返回在指定时间之前更新的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| updated_after | string | 否 | 返回在指定时间之后更新的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Pull Request ID |
| title | string | Pull Request标题 |
| url | string | API URL |
| html_url | string | Pull Request页面URL |
| number | integer | Pull Request编号 |
| state | string | Pull Request状态 |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| head | object | 源分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| base | object | 目标分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |

### 响应示例

```json
[
  {
    "id": 100,
    "title": "新增功能",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1",
    "html_url": "https://gitcode.com/owner/repo/pulls/1",
    "number": 1,
    "state": "open",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    },
    "head": {
      "label": "feature-branch",
      "ref": "feature-branch",
      "sha": "abc123"
    },
    "base": {
      "label": "main",
      "ref": "main",
      "sha": "def456"
    },
    "created_at": "2024-01-01T00:00:00+08:00",
    "updated_at": "2024-01-01T00:00:00+08:00",
    "merged_at": null,
    "closed_at": null
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/orgs/:org/pull_requests?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/orgs/:org/pull_requests"
params = {
    "access_token": "YOUR_TOKEN",
    "state": "open",
    "page": 1
}

response = requests.get(url, params=params)
print(response.json())
```
