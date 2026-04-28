# 更新Commit评论

更新指定的提交评论内容。

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-comments-id

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | string | 是 | 评论ID |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| body | string | 是 | 评论内容 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| body | string | 评论内容 |
| created_at | string | 创建时间 |
| id | integer | 评论ID |
| target | object | 目标对象 |
| updated_at | string | 更新时间 |
| user | object | 用户信息 |
| └─ id | integer | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ type | string | 用户类型 |

### 响应示例

```json
{
  "body": "更新后的评论内容",
  "created_at": "2024-11-06T09:43:23+08:00",
  "id": 1492393,
  "target": {},
  "updated_at": "2024-11-14T18:44:53+08:00",
  "user": {
    "id": 496,
    "login": "xiaogang",
    "name": "xiaogang",
    "type": "User"
  }
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "更新后的评论内容"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/comments/comment_id"
params = {
}
data = {
    "body": "更新后的评论内容"
}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
