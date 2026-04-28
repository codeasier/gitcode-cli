# 获取某个Pull Request的所有评论

获取某个Pull Request的所有评论

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-comments

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 当前的页码:默认为 1 |
| per_page | integer | 否 | 每页的数量，最大为 100，默认 20 |
| direction | string | 否 | 升序/降序(asc/desc) |
| comment_type | string | 否 | 筛选评论类型。代码行评论/pr普通评论:diff_comment/pr_comment |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 评论ID |
| discussion_id | string | 讨论id |
| body | string | 评论内容 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| user | object | 用户信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| └─ html_url | string | 用户主页URL |
| comment_type | string | 评论类型 |
| resolved | boolean | 是否已解决 |
| diff_file | string | 差异文件 |
| diff_position | object | 差异位置信息 |
| └─ start_new_line | integer | 起始新行号 |
| └─ end_new_line | integer | 结束新行号 |
| └─ start_old_line | integer | 起始旧行号 |
| └─ end_old_line | integer | 结束旧行号 |
| reply | array | 回复列表 |
| └─ id | integer | 回复ID |
| └─ body | string | 回复内容 |
| └─ created_at | string | 创建时间 |
| └─ updated_at | string | 更新时间 |
| └─ user | object | 用户信息 |
|    └─ id | string | 用户ID |
|    └─ login | string | 用户登录名 |
|    └─ name | string | 用户昵称 |
|    └─ avatar_url | string | 用户头像URL |
|    └─ html_url | string | 用户主页URL |

### 响应示例

```json
[
  {
    "id": 123456,
    "discussion_id": "abc123",
    "body": "这是一条评论",
    "created_at": "2024-04-19T07:48:59.755+00:00",
    "updated_at": "2024-04-19T07:48:59.755+00:00",
    "user": {
      "id": "708",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png",
      "html_url": "https://gitcode.com/username"
    },
    "comment_type": "pr_comment",
    "resolved": false,
    "diff_file": "src/main.py",
    "diff_position": {
      "start_new_line": 10,
      "end_new_line": 15,
      "start_old_line": 8,
      "end_old_line": 12
    },
    "reply": [
      {
        "id": 789,
        "body": "回复内容",
        "created_at": "2024-04-19T08:00:00+00:00",
        "updated_at": "2024-04-19T08:00:00+00:00",
        "user": {
          "id": "123",
          "login": "replier",
          "name": "回复者",
          "avatar_url": "https://gitcode.com/avatar2.png",
          "html_url": "https://gitcode.com/replier"
        }
      }
    ]
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments?access_token=YOUR_TOKEN&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
