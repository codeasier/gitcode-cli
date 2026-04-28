# 获取Pull Request评论的修改历史

获取Pull Request评论的修改历史

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/comment/:comment_id/modify_history`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-comment-comment-id-modify-history

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| comment_id | string | 是 | 评论的id |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 历史记录ID |
| created_at | string | 创建时间 |
| updated_at | string | 修改时间 |
| deleted | boolean | 是否已删除 |
| created | boolean | 是否是创建 |
| content | string | 修改后的内容 |
| user | object | 用户信息 |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ object_id | string | 对象ID |
| updated_user | object | 更新用户信息 |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ object_id | string | 对象ID |

### 响应示例

```json
[
  {
    "id": "abc123",
    "created_at": "2024-01-01T00:00:00+08:00",
    "updated_at": "2024-01-02T00:00:00+08:00",
    "deleted": false,
    "created": true,
    "content": "修改后的评论内容",
    "user": {
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png",
      "object_id": "123"
    },
    "updated_user": {
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png",
      "object_id": "123"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comment/:comment_id/modify_history?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comment/:comment_id/modify_history"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
