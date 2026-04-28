# 获取单个Pull Request

获取单个Pull Request

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Pull Request ID |
| iid | integer | Pull Request序号 |
| number | integer | Pull Request编号 |
| title | string | Pull Request标题 |
| body | string | Pull Request描述 |
| state | string | Pull Request状态 |
| html_url | string | Pull Request页面URL |
| url | string | API URL |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| head | object | 源分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| └─ user | object | 用户信息 |
| └─ repo | object | 仓库信息 |
| base | object | 目标分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| └─ user | object | 用户信息 |
| └─ repo | object | 仓库信息 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |
| merged | boolean | 是否已合并 |
| mergeable | boolean | 是否可合并 |
| mergeable_state | string | 可合并状态 |
| merged_by | object | 合并者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| comments | integer | 评论数 |
| commits | integer | 提交数 |
| additions | integer | 新增行数 |
| deletions | integer | 删除行数 |
| changed_files | integer | 变更文件数 |
| draft | boolean | 是否为草稿 |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| └─ color | string | 标签颜色 |
| assignees | array | 审查人列表 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| testers | array | 测试人列表 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |

### 响应示例

```json
{
  "id": 100,
  "iid": 1,
  "number": 1,
  "title": "新增功能",
  "body": "这是一个新增功能的PR",
  "state": "open",
  "html_url": "https://gitcode.com/owner/repo/pulls/1",
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1",
  "user": {
    "id": "123",
    "login": "username",
    "name": "用户昵称",
    "avatar_url": "https://gitcode.com/avatar.png"
  },
  "head": {
    "label": "feature-branch",
    "ref": "feature-branch",
    "sha": "abc123",
    "user": {},
    "repo": {}
  },
  "base": {
    "label": "main",
    "ref": "main",
    "sha": "def456",
    "user": {},
    "repo": {}
  },
  "created_at": "2024-01-01T00:00:00+08:00",
  "updated_at": "2024-01-01T00:00:00+08:00",
  "merged_at": null,
  "closed_at": null,
  "merged": false,
  "mergeable": true,
  "mergeable_state": "clean",
  "merged_by": null,
  "comments": 5,
  "commits": 3,
  "additions": 100,
  "deletions": 50,
  "changed_files": 10,
  "draft": false,
  "labels": [
    {
      "id": 1,
      "name": "enhancement",
      "color": "#84b6eb"
    }
  ],
  "assignees": [
    {
      "id": "456",
      "login": "reviewer",
      "name": "审查者",
      "avatar_url": "https://gitcode.com/avatar2.png"
    }
  ],
  "testers": []
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
