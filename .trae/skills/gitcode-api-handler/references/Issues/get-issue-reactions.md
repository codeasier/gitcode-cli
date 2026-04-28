# 获取issue的表态列表

获取指定 Issue 的所有表态列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/:number/user_reactions`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-number-user-reactions

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回表态对象数组

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
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/user_reactions?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/user_reactions"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
