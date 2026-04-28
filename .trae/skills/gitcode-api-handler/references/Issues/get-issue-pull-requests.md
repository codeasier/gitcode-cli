# 获取 issue 关联的 pull requests

获取指定 Issue 关联的所有 Pull Requests

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/:number/pull_requests`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-number-pull-requests

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| mode | string | 否 | 模式参数 |

## 响应

### 响应结构

返回 Pull Request 对象数组

### 响应示例

```json
[
  {
    "id": 123456,
    "number": 1,
    "state": "open",
    "title": "PR标题",
    "body": "PR描述",
    "html_url": "https://gitcode.com/owner/repo/pull/1",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户名"
    },
    "created_at": "2024-01-01T10:00:00+08:00",
    "updated_at": "2024-01-01T10:00:00+08:00"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/pull_requests?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/pull_requests"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
