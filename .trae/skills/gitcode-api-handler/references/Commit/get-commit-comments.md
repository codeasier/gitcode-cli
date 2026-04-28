# 获取单个commit评论

获取指定提交的所有评论列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/commits/:ref/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-commits-ref-comments

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| ref | string | 是 | commit的sha(SHA值) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量,最大为100,默认20 |

## 响应

### 响应结构 (array)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| body | string | 评论内容 |
| created_at | string | 创建时间 |
| id | integer | 评论ID |
| updated_at | string | 更新时间 |
| user | object | 用户信息 |
| └─ id | integer | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ type | string | 用户类型 |

### 响应示例

```json
[
  {
    "body": "这是一条评论内容",
    "created_at": "2024-11-19T11:22:50+08:00",
    "id": 13837749,
    "updated_at": "2024-11-19T11:22:50+08:00",
    "user": {
      "id": 173794,
      "login": "xiaogang",
      "name": "肖刚",
      "type": "User"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/commits/:ref/comments?access_token=YOUR_TOKEN&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/commits/sha/comments"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
