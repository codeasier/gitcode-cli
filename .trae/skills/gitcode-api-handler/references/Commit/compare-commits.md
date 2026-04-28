# Commits对比

比较两个提交之间的差异。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/compare/:base...:head`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-compare-base-head

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| base | string | 是 | 基准提交的SHA值或分支名 |
| head | string | 是 | 比较提交的SHA值或分支名 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| straight | string | 否 | 是否使用直线比较(默认false) |
| suffix | string | 否 | 后缀 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| url | string | 比较结果URL |
| html_url | string | 比较结果HTML页面URL |
| permalink_url | string | 永久链接URL |
| diff_url | string | diff文件URL |
| patch_url | string | patch文件URL |
| base_commit | object | 基准提交信息 |
| └─ sha | string | 提交SHA值 |
| └─ url | string | 提交URL |
| └─ html_url | string | 提交HTML页面URL |
| merge_base_commit | object | 合并基准提交信息 |
| └─ sha | string | 提交SHA值 |
| └─ url | string | 提交URL |
| └─ html_url | string | 提交HTML页面URL |
| status | string | 比较状态(ahead/behind/diverged/identical) |
| ahead_by | integer | 领先的提交数 |
| behind_by | integer | 落后的提交数 |
| total_commits | integer | 总提交数 |
| commits | array | 提交列表 |
| └─ sha | string | 提交SHA值 |
| └─ url | string | 提交URL |
| └─ html_url | string | 提交HTML页面URL |
| └─ author | object | 作者信息 |
|    └─ id | integer | 用户ID |
|    └─ login | string | 用户登录名 |
|    └─ name | string | 用户昵称 |
|    └─ avatar_url | string | 用户头像URL |
| files | array | 文件变更列表 |
| └─ filename | string | 文件名 |
| └─ additions | integer | 新增行数 |
| └─ deletions | integer | 删除行数 |
| └─ changes | integer | 总变更数 |
| └─ status | string | 文件状态 |
| └─ raw_url | string | 原始文件URL |
| └─ blob_url | string | blob对象URL |
| └─ patch | string | 补丁信息 |

### 响应示例

```json
{
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/compare/base...head",
  "html_url": "https://gitcode.com/owner/repo/compare/base...head",
  "permalink_url": "https://gitcode.com/owner/repo/compare/abc123...def456",
  "diff_url": "https://gitcode.com/owner/repo/compare/base...head.diff",
  "patch_url": "https://gitcode.com/owner/repo/compare/base...head.patch",
  "base_commit": {
    "sha": "abc123",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/abc123",
    "html_url": "https://gitcode.com/owner/repo/commit/abc123"
  },
  "merge_base_commit": {
    "sha": "abc123",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/abc123",
    "html_url": "https://gitcode.com/owner/repo/commit/abc123"
  },
  "status": "ahead",
  "ahead_by": 2,
  "behind_by": 0,
  "total_commits": 2,
  "commits": [
    {
      "sha": "def456",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/def456",
      "html_url": "https://gitcode.com/owner/repo/commit/def456",
      "author": {
        "id": 123,
        "login": "testuser",
        "name": "Test User",
        "avatar_url": "https://gitcode.com/avatar.jpg"
      }
    }
  ],
  "files": [
    {
      "filename": "README.md",
      "additions": 10,
      "deletions": 2,
      "changes": 12,
      "status": "modified",
      "raw_url": "https://gitcode.com/owner/repo/raw/def456/README.md",
      "blob_url": "https://gitcode.com/owner/repo/blob/def456/README.md",
      "patch": "@@ -1,2 +1,10 @@"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/compare/:base...:head?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/compare/base...head"
params = {
    "access_token": "YOUR_TOKEN",
    "straight": "false"
}

response = requests.get(url, params=params)
print(response.json())
```
