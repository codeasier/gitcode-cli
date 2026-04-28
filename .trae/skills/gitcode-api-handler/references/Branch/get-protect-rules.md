# 获取保护分支规则列表

获取指定仓库的所有保护分支规则。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/protect_branches`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-protect-branches

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

## 响应

### 响应结构 (array)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | 保护规则id |
| wildcard | string | 分支名称模式 |
| pusher | string | 允许推送的用户 |
| merger | string | 允许合并的用户 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
[
  {
    "id": 1,
    "wildcard": "release-*",
    "pusher": "user1,user2",
    "merger": "user1",
    "created_at": "2024-01-01T12:00:00.000+08:00",
    "updated_at": "2024-01-01T12:00:00.000+08:00"
  },
  {
    "id": 2,
    "wildcard": "main",
    "pusher": "",
    "merger": "admin",
    "created_at": "2024-01-01T12:00:00.000+08:00",
    "updated_at": "2024-01-01T12:00:00.000+08:00"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/protect_branches?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/protect_branches"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
