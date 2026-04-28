# 获取代码量贡献

获取指定仓库的代码量贡献统计。

## 基本信息

- **方法**: GET
- **路径**: `/:owner/:repo/repository/commit_statistics`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-owner-repo-repository-commit-statistics

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| branch_name | string | 否 | 分支名称 |
| author | string | 否 | 作者 |
| only_self | string | 否 | 是否仅统计自己 |
| since | string | 否 | 起始日期 |
| until | string | 否 | 结束日期 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| total | object | 总体统计 |
| └─ additions | integer | 新增行数 |
| └─ deletions | integer | 删除行数 |
| └─ commits | integer | 提交次数 |
| authors | array | 作者统计列表 |
| └─ author | object | 作者信息 |
|    └─ id | integer | 用户ID |
|    └─ login | string | 用户登录名 |
|    └─ name | string | 用户昵称 |
|    └─ avatar_url | string | 用户头像URL |
| └─ additions | integer | 新增行数 |
| └─ deletions | integer | 删除行数 |
| └─ commits | integer | 提交次数 |

### 响应示例

```json
{
  "total": {
    "additions": 1000,
    "deletions": 500,
    "commits": 50
  },
  "authors": [
    {
      "author": {
        "id": 123,
        "login": "testuser",
        "name": "Test User",
        "avatar_url": "https://gitcode.com/avatar.jpg"
      },
      "additions": 800,
      "deletions": 400,
      "commits": 40
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/:owner/:repo/repository/commit_statistics?access_token=YOUR_TOKEN&branch_name=main" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/owner/repo/repository/commit_statistics"
params = {
    "access_token": "YOUR_TOKEN",
    "branch_name": "main",
    "since": "2024-01-01",
    "until": "2024-12-31"
}

response = requests.get(url, params=params)
print(response.json())
```
