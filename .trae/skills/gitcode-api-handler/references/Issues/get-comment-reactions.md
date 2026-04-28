# 获取issue评论的表态列表

获取指定 Issue 评论的所有表态列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/comment/:comment_id/user_reactions`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-comment-comment-id-user-reactions

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
| page | string | 否 | 当前页码 |
| per_page | string | 否 | 每页数量 |
| emoji_name | string | 否 | emoji表情,可选: like, dislike, smile, confused, love, rocket, eyes, party |

## 响应

### 响应结构

返回表态对象数组,每个对象包含以下字段:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 表态ID |
| emoji | string | emoji表情 |
| emoji_name | string | emoji表情枚举值 |
| user | object | 用户信息 |
| user.login | string | 用户登录名 |
| user.name | string | 用户名称 |
| user.avatar_url | string | 用户头像URL |
| user.object_id | string | 对象ID |

### 响应示例

```json
[
  {
    "id": "123",
    "emoji": "👍",
    "emoji_name": "like",
    "user": {
      "login": "username",
      "name": "用户名",
      "avatar_url": "https://gitcode.com/avatar.jpg",
      "object_id": "456"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/comment/:comment_id/user_reactions?access_token=YOUR_TOKEN&emoji_name=like" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/comment/271624/user_reactions"
params = {
    "access_token": "YOUR_TOKEN",
    "emoji_name": "like"
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
