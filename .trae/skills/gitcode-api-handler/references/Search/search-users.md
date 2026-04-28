# 搜索用户

根据关键字搜索用户信息。

## 基本信息

- **方法**: GET
- **路径**: `/search/users`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-search-users

## 请求参数

### 路径参数

无

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| q | string | 是 | 搜索关键字 |
| sort | string | 否 | 排序字段，可选值：`best_match`（默认）、`followers`、`repositories`、`joined` |
| order | string | 否 | 排序顺序，可选值：`desc`（默认）、`asc` |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_count | integer | 搜索结果总数 |
| incomplete_results | boolean | 结果是否不完整 |
| items | array | 用户列表 |
| items[].id | integer | 用户ID |
| items[].login | string | 用户登录名 |
| items[].name | string | 用户名称 |
| items[].avatar_url | string | 用户头像URL |
| items[].html_url | string | 用户主页URL |
| items[].type | string | 用户类型（User/Organization） |
| items[].bio | string | 用户简介 |
| items[].location | string | 用户位置 |
| items[].blog | string | 用户博客 |
| items[].followers | integer | 粉丝数 |
| items[].following | integer | 关注数 |
| items[].public_repos | integer | 公开仓库数 |
| items[].score | number | 搜索匹配分数 |

### 响应示例

```json
{
  "total_count": 123,
  "incomplete_results": false,
  "items": [
    {
      "id": 1,
      "login": "octocat",
      "name": "The Octocat",
      "avatar_url": "https://gitcode.com/avatars/u/1",
      "html_url": "https://gitcode.com/octocat",
      "type": "User",
      "bio": "GitCode mascot",
      "location": "San Francisco",
      "blog": "https://octocat.github.com",
      "followers": 1000,
      "following": 100,
      "public_repos": 50,
      "score": 95.5
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/search/users?q=octocat&sort=followers&order=desc&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/search/users"
params = {
    "q": "octocat",
    "sort": "followers",
    "order": "desc",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```

## 注意事项

- 搜索接口不需要认证即可访问公开用户信息
- 认证用户可以搜索更多私有信息
- 注意速率限制，避免频繁请求
