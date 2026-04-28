# 创建commit评论

为指定的提交创建评论。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/commits/:sha/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-commits-sha-comments

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

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| body | string | 是 | 评论内容 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 评论ID |
| body | string | 评论内容 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
{
  "id": "12312sadsa",
  "body": "这是一条评论内容",
  "created_at": "2024-03-28T11:19:33+08:00",
  "updated_at": "2024-03-28T11:19:33+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/commits/:sha/comments?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "这是一条评论内容"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/commits/sha/comments"
params = {
}
data = {
    "body": "这是一条评论内容"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
