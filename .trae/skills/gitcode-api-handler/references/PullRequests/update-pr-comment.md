# 编辑评论

编辑评论

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/pulls/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-comments-id

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | integer | 是 | 评论的ID |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| body | string | 是 | 评论内容 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 评论ID |
| body | string | 评论内容 |
| updated_at | string | 更新时间 |

### 响应示例

```json
{
  "id": 1486664,
  "body": "更新后的评论内容",
  "updated_at": "2024-09-27T15:00:00+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "更新后的评论内容"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id"
params = {"access_token": "YOUR_TOKEN"}
data = {"body": "更新后的评论内容"}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
