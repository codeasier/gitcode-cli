# 获取Pull Request某条评论

获取Pull Request某条评论

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-comments-id

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | string | 是 | 评论 ID |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 评论ID |
| discussion_id | string | 讨论id |
| body | string | 评论内容 |
| comment_type | string | 评论类型 |
| user | object | 用户信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ type | string | 用户类型 |
| target | object | 目标信息 |
| └─ issue | object | Issue信息 |
|    └─ id | integer | Issue ID |
|    └─ title | string | Issue标题 |
|    └─ number | string | Issue编号 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| position | object | 位置信息 |
| └─ base_sha | string | 基础SHA |
| └─ start_sha | string | 起始SHA |
| └─ head_sha | string | 头部SHA |
| └─ old_path | string | 旧路径 |
| └─ new_path | string | 新路径 |
| └─ position_type | string | 位置类型 |
| └─ old_line | integer | 旧行号 |
| └─ new_line | integer | 新行号 |
| └─ start_old_line | integer | 起始旧行号 |
| └─ start_new_line | integer | 起始新行号 |

### 响应示例

```json
{
  "id": 1486664,
  "discussion_id": "abc123",
  "body": "这是一条评论",
  "comment_type": "DiscussionNote",
  "user": {
    "id": "303745",
    "login": "yinlin",
    "name": "yinlin-昵称",
    "type": "User"
  },
  "target": {
    "issue": {
      "id": 478892,
      "title": "测试Issue",
      "number": "123"
    }
  },
  "created_at": "2024-09-27T14:58:51+08:00",
  "updated_at": "2024-09-27T14:58:51+08:00",
  "position": {
    "base_sha": "abc123",
    "start_sha": "def456",
    "head_sha": "ghi789",
    "old_path": "src/old.py",
    "new_path": "src/new.py",
    "position_type": "text",
    "old_line": 10,
    "new_line": 15,
    "start_old_line": 8,
    "start_new_line": 12
  }
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
