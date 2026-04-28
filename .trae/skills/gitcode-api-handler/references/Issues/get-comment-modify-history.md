# 获取issue评论的修改历史

获取指定 Issue 评论的所有修改历史记录

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/comment/:comment_id/modify_history`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-comment-comment-id-modify-history

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| comment_id | string | 是 | 评论的id |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回修改历史对象数组,每个对象包含以下字段:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 历史记录ID |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| deleted | boolean | 是否已删除 |
| created | boolean | 是否是创建 |
| content | string | 修改后的内容 |
| user | object | 用户信息 |
| user.login | string | 用户登录名 |
| user.name | string | 用户名称 |
| user.avatar_url | string | 用户头像URL |
| user.object_id | string | 对象ID |
| updated_user | object | 更新用户信息 |
| updated_user.login | string | 更新用户登录名 |
| updated_user.name | string | 更新用户名称 |
| updated_user.avatar_url | string | 更新用户头像URL |
| updated_user.object_id | string | 更新用户对象ID |

### 响应示例

```json
[
  {
    "id": "1",
    "created_at": "2024-01-01T10:00:00+08:00",
    "updated_at": "2024-01-01T10:00:00+08:00",
    "deleted": false,
    "created": true,
    "content": "这是评论内容",
    "user": {
      "login": "username",
      "name": "用户名",
      "avatar_url": "https://gitcode.com/avatar.jpg",
      "object_id": "123"
    },
    "updated_user": {
      "login": "username",
      "name": "用户名",
      "avatar_url": "https://gitcode.com/avatar.jpg",
      "object_id": "123"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/comment/:comment_id/modify_history?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/comment/271624/modify_history"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
