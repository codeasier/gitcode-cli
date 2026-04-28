# 获取某Pull Request的所有Commit信息

获取某Pull Request的所有Commit信息

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/commits`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-commits

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| sha | string | 提交SHA |
| html_url | string | 提交页面URL |
| url | string | API URL |
| author | object | 作者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ email | string | 用户邮箱 |
| committer | object | 提交者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ email | string | 用户邮箱 |
| commit | object | 提交信息 |
| └─ message | string | 提交消息 |
| └─ author | object | 作者信息 |
|    └─ name | string | 作者名称 |
|    └─ email | string | 作者邮箱 |
|    └─ date | string | 提交日期 |
| └─ committer | object | 提交者信息 |
|    └─ name | string | 提交者名称 |
|    └─ email | string | 提交者邮箱 |
|    └─ date | string | 提交日期 |
| parents | array | 父提交列表 |
| └─ sha | string | 父提交SHA |
| └─ html_url | string | 父提交页面URL |
| └─ url | string | 父提交API URL |

### 响应示例

```json
[
  {
    "sha": "abc123def456",
    "html_url": "https://gitcode.com/owner/repo/commit/abc123",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/abc123",
    "author": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png",
      "email": "user@example.com"
    },
    "committer": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png",
      "email": "user@example.com"
    },
    "commit": {
      "message": "新增功能",
      "author": {
        "name": "用户昵称",
        "email": "user@example.com",
        "date": "2024-01-01T00:00:00+08:00"
      },
      "committer": {
        "name": "用户昵称",
        "email": "user@example.com",
        "date": "2024-01-01T00:00:00+08:00"
      }
    },
    "parents": [
      {
        "sha": "parent123",
        "html_url": "https://gitcode.com/owner/repo/commit/parent123",
        "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/parent123"
      }
    ]
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/commits?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/commits"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
