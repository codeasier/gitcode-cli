# 搜索 Issues

根据关键字搜索 Issues 和 Pull Requests。

## 基本信息

- **方法**: GET
- **路径**: `/search/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-search-issues

## 请求参数

### 路径参数

无

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| q | string | 是 | 搜索关键字，支持搜索限定符 |
| sort | string | 否 | 排序字段，可选值：`best_match`（默认）、`created`、`updated`、`comments` |
| order | string | 否 | 排序顺序，可选值：`desc`（默认）、`asc` |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

### 搜索限定符

| 限定符 | 示例 | 说明 |
|--------|------|------|
| type | `type:issue` / `type:pr` | 指定搜索类型 |
| state | `state:open` / `state:closed` | 指定状态 |
| author | `author:username` | 指定作者 |
| assignee | `assignee:username` | 指定指派人 |
| repo | `repo:owner/repo` | 指定仓库 |
| label | `label:bug` | 指定标签 |
| milestone | `milestone:v1.0` | 指定里程碑 |
| created | `created:>2024-01-01` | 指定创建时间 |
| updated | `updated:>2024-01-01` | 指定更新时间 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_count | integer | 搜索结果总数 |
| incomplete_results | boolean | 结果是否不完整 |
| items | array | Issue/PR 列表 |
| items[].id | integer | Issue/PR ID |
| items[].number | integer | Issue/PR 编号 |
| items[].title | string | 标题 |
| items[].body | string | 内容 |
| items[].html_url | string | 页面URL |
| items[].state | string | 状态（open/closed） |
| items[].user | object | 创建者信息 |
| items[].user.id | integer | 用户ID |
| items[].user.login | string | 用户登录名 |
| items[].user.avatar_url | string | 用户头像URL |
| items[].labels | array | 标签列表 |
| items[].labels[].id | integer | 标签ID |
| items[].labels[].name | string | 标签名称 |
| items[].labels[].color | string | 标签颜色 |
| items[].assignees | array | 指派人列表 |
| items[].milestone | object | 里程碑信息 |
| items[].milestone.id | integer | 里程碑ID |
| items[].milestone.title | string | 里程碑标题 |
| items[].comments | integer | 评论数 |
| items[].created_at | string | 创建时间 |
| items[].updated_at | string | 更新时间 |
| items[].closed_at | string | 关闭时间 |
| items[].pull_request | object | PR 信息（仅 PR 类型） |
| items[].score | number | 搜索匹配分数 |

### 响应示例

```json
{
  "total_count": 456,
  "incomplete_results": false,
  "items": [
    {
      "id": 1,
      "number": 123,
      "title": "Bug: 修复登录问题",
      "body": "登录时出现错误...",
      "html_url": "https://gitcode.com/owner/repo/issues/123",
      "state": "open",
      "user": {
        "id": 1,
        "login": "developer",
        "avatar_url": "https://gitcode.com/avatars/u/1"
      },
      "labels": [
        {
          "id": 1,
          "name": "bug",
          "color": "ff0000"
        }
      ],
      "assignees": [
        {
          "id": 2,
          "login": "maintainer",
          "avatar_url": "https://gitcode.com/avatars/u/2"
        }
      ],
      "milestone": {
        "id": 1,
        "title": "v1.0"
      },
      "comments": 5,
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-02T14:30:00Z",
      "closed_at": null,
      "score": 88.5
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/search/issues?q=bug+state:open+repo:owner/repo&sort=created&order=desc&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/search/issues"
params = {
    "q": "bug state:open repo:owner/repo",
    "sort": "created",
    "order": "desc",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```

## 注意事项

- 搜索接口不需要认证即可访问公开 Issue/PR 信息
- 可以组合多个搜索限定符进行精确搜索
- 注意速率限制，避免频繁请求
