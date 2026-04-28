# 仓库的某个提交

获取指定仓库中某个提交的详细信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/commits/:sha`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-commits-sha

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| sha | string | 是 | commit的id(SHA值) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| show_diff | string | 否 | 是否显示diff信息 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| sha | string | 提交的SHA值 |
| url | string | 提交详情的URL |
| html_url | string | 提交的HTML页面URL |
| comments_url | string | 提交评论的URL |
| commit | object | 提交详细信息 |
| └─ author | object | 作者信息 |
|    └─ name | string | 作者名称 |
|    └─ email | string | 作者邮箱 |
|    └─ date | string | 提交日期 |
| └─ committer | object | 提交者信息 |
|    └─ name | string | 提交者名称 |
|    └─ email | string | 提交者邮箱 |
|    └─ date | string | 提交日期 |
| └─ message | string | 提交信息 |
| └─ tree | object | 树对象信息 |
|    └─ sha | string | 树对象的SHA值 |
|    └─ url | string | 树对象的URL |
| author | object | 作者详细信息 |
| └─ id | integer | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ type | string | 用户类型 |
| committer | object | 提交者详细信息 |
| └─ id | integer | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ type | string | 用户类型 |
| parents | array | 父提交列表 |
| └─ sha | string | 父提交的SHA值 |
| └─ url | string | 父提交的URL |
| └─ html_url | string | 父提交的HTML页面URL |
| files | array | 文件变更列表 |
| └─ filename | string | 文件名 |
| └─ additions | integer | 新增行数 |
| └─ deletions | integer | 删除行数 |
| └─ changes | integer | 总变更数 |
| └─ status | string | 文件状态(added/modified/removed) |
| └─ raw_url | string | 原始文件URL |
| └─ blob_url | string | blob对象URL |
| └─ patch | string | 补丁信息 |

### 响应示例

```json
{
  "sha": "2912b8f2328e798f7d544272ffaebfccccb598ab",
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/2912b8f2328e798f7d544272ffaebfccccb598ab",
  "html_url": "https://gitcode.com/owner/repo/commit/2912b8f2328e798f7d544272ffaebfccccb598ab",
  "comments_url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/2912b8f2328e798f7d544272ffaebfccccb598ab/comments",
  "commit": {
    "author": {
      "name": "test",
      "email": "test@example.com",
      "date": "2024-01-01T12:00:00+08:00"
    },
    "committer": {
      "name": "test",
      "email": "test@example.com",
      "date": "2024-01-01T12:00:00+08:00"
    },
    "message": "Initial commit",
    "tree": {
      "sha": "abc123def456",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo/trees/abc123def456"
    }
  },
  "author": {
    "id": 123,
    "login": "testuser",
    "name": "Test User",
    "avatar_url": "https://gitcode.com/avatar.jpg",
    "type": "User"
  },
  "committer": {
    "id": 123,
    "login": "testuser",
    "name": "Test User",
    "avatar_url": "https://gitcode.com/avatar.jpg",
    "type": "User"
  },
  "parents": [
    {
      "sha": "parent123sha",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/parent123sha",
      "html_url": "https://gitcode.com/owner/repo/commit/parent123sha"
    }
  ],
  "files": [
    {
      "filename": "README.md",
      "additions": 10,
      "deletions": 2,
      "changes": 12,
      "status": "modified",
      "raw_url": "https://gitcode.com/owner/repo/raw/2912b8f/README.md",
      "blob_url": "https://gitcode.com/owner/repo/blob/2912b8f/README.md",
      "patch": "@@ -1,2 +1,10 @@"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/commits/:sha?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/commits/sha"
params = {
    "access_token": "YOUR_TOKEN",
    "show_diff": "true"
}

response = requests.get(url, params=params)
print(response.json())
```
