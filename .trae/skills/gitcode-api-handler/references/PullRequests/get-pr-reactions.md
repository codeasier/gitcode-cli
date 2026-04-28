# 获取Pull Request的表态列表

获取Pull Request的表态列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/user_reactions`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-user-reactions

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Pull Request 编号(区分大小写，无需添加 # 号) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | string | 否 | 当前页码 |
| per_page | string | 否 | 每页数量 |
| emoji_name | string | 否 | emoji表情，可选：like，dislike，smile，confused，love，rocket，eyes，party |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 表态ID |
| emoji | string | emoji表情 |
| emoji_name | string | emoji表情枚举值 |
| user | object | 用户信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |

### 响应示例

```json
[
  {
    "id": "abc123",
    "emoji": "👍",
    "emoji_name": "like",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/user_reactions?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/user_reactions"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
