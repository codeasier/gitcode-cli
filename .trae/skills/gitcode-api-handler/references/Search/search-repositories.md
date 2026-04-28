# 搜索仓库

根据关键字搜索仓库信息。

## 基本信息

- **方法**: GET
- **路径**: `/search/repositories`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-search-repositories

## 请求参数

### 路径参数

无

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| q | string | 是 | 搜索关键字，支持搜索限定符 |
| sort | string | 否 | 排序字段，可选值：`best_match`（默认）、`stars`、`forks`、`updated` |
| order | string | 否 | 排序顺序，可选值：`desc`（默认）、`asc` |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

### 搜索限定符

| 限定符 | 示例 | 说明 |
|--------|------|------|
| user | `user:username` | 指定用户/组织 |
| org | `org:orgname` | 指定组织 |
| language | `language:python` | 指定编程语言 |
| topic | `topic:api` | 指定主题 |
| stars | `stars:>100` | 指定 star 数量 |
| forks | `forks:>10` | 指定 fork 数量 |
| size | `size:<1000` | 指定仓库大小（KB） |
| created | `created:>2024-01-01` | 指定创建时间 |
| pushed | `pushed:>2024-01-01` | 指定最后推送时间 |
| license | `license:mit` | 指定许可证 |
| is | `is:public` / `is:private` | 指定可见性 |
| fork | `fork:true` | 是否为 fork 仓库 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_count | integer | 搜索结果总数 |
| incomplete_results | boolean | 结果是否不完整 |
| items | array | 仓库列表 |
| items[].id | integer | 仓库ID |
| items[].name | string | 仓库名称 |
| items[].full_name | string | 仓库全名（owner/repo） |
| items[].owner | object | 所有者信息 |
| items[].owner.id | integer | 用户ID |
| items[].owner.login | string | 用户登录名 |
| items[].owner.avatar_url | string | 用户头像URL |
| items[].owner.type | string | 用户类型（User/Organization） |
| items[].private | boolean | 是否私有 |
| items[].html_url | string | 仓库页面URL |
| items[].description | string | 仓库描述 |
| items[].fork | boolean | 是否为 fork 仓库 |
| items[].url | string | API URL |
| items[].language | string | 主要编程语言 |
| items[].stargazers_count | integer | Star 数量 |
| items[].watchers_count | integer | Watch 数量 |
| items[].forks_count | integer | Fork 数量 |
| items[].open_issues_count | integer | 公开 Issue 数量 |
| items[].default_branch | string | 默认分支 |
| items[].topics | array | 主题列表 |
| items[].license | object | 许可证信息 |
| items[].license.key | string | 许可证标识 |
| items[].license.name | string | 许可证名称 |
| items[].license.spdx_id | string | SPDX ID |
| items[].created_at | string | 创建时间 |
| items[].updated_at | string | 更新时间 |
| items[].pushed_at | string | 最后推送时间 |
| items[].score | number | 搜索匹配分数 |

### 响应示例

```json
{
  "total_count": 789,
  "incomplete_results": false,
  "items": [
    {
      "id": 1,
      "name": "awesome-project",
      "full_name": "developer/awesome-project",
      "owner": {
        "id": 1,
        "login": "developer",
        "avatar_url": "https://gitcode.com/avatars/u/1",
        "type": "User"
      },
      "private": false,
      "html_url": "https://gitcode.com/developer/awesome-project",
      "description": "一个很棒的项目",
      "fork": false,
      "url": "https://api.gitcode.com/api/v5/repos/developer/awesome-project",
      "language": "Python",
      "stargazers_count": 1000,
      "watchers_count": 500,
      "forks_count": 200,
      "open_issues_count": 50,
      "default_branch": "main",
      "topics": ["python", "api", "web"],
      "license": {
        "key": "mit",
        "name": "MIT License",
        "spdx_id": "MIT"
      },
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-02T14:30:00Z",
      "pushed_at": "2024-01-03T16:45:00Z",
      "score": 92.5
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/search/repositories?q=python+stars:>100+language:python&sort=stars&order=desc&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/search/repositories"
params = {
    "q": "python stars:>100 language:python",
    "sort": "stars",
    "order": "desc",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```

## 注意事项

- 搜索接口不需要认证即可访问公开仓库信息
- 可以组合多个搜索限定符进行精确搜索
- 注意速率限制，避免频繁请求
- 认证用户可以搜索自己有权限访问的私有仓库
