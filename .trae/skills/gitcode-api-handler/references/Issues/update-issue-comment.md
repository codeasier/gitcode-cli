# 更新Issue某条评论

更新指定 Issue 的某条评论

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/issues/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-issues-comments-id

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | string | 是 | 评论 ID |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| body | string | 是 | 评论内容 |

## 响应

### 响应结构

| 字段 | 类型 | 描述 |
|------|------|------|
| id | integer | 评论ID |
| body | string | 更新后的评论内容 |
| user | object | 评论用户信息 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
{
  "id": 271624,
  "body": "更新后的评论内容",
  "user": {
    "id": "123",
    "login": "username",
    "name": "用户名"
  },
  "created_at": "2024-01-01T10:00:00+08:00",
  "updated_at": "2024-01-02T15:30:00+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "更新后的评论内容"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/comments/271624"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}
data = {
    "body": "更新后的评论内容"
}

response = requests.patch(url, headers=headers, params=params, json=data)
print(response.json())
```
