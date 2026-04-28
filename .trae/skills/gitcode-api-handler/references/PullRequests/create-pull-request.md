# 创建Pull Request

创建Pull Request

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/pulls`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| title | string | 是 | Pull Request标题 |
| head | string | 是 | 源分支名称 |
| base | string | 是 | 目标分支名称 |
| body | string | 否 | Pull Request描述 |
| milestone_number | integer | 否 | 里程碑编号 |
| labels | string | 否 | 标签名称，多个用逗号分隔 |
| issue | string | 否 | 关联的Issue编号 |
| assignees | string | 否 | 审查人用户名，多个用逗号分隔 |
| testers | string | 否 | 测试人用户名，多个用逗号分隔 |
| prune_source_branch | boolean | 否 | 合并后删除源分支 |
| draft | boolean | 否 | 是否为草稿 |
| squash | boolean | 否 | 是否使用squash合并 |
| squash_commit_message | string | 否 | Squash合并时的提交信息 |
| fork_path | string | 否 | Fork仓库路径 |
| close_related_issue | boolean | 否 | 是否关闭关联的Issue |

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
| base | object | 目标分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |
| mergeable | boolean | 是否可合并 |
| merged | boolean | 是否已合并 |
| closed | boolean | 是否已关闭 |
| draft | boolean | 是否为草稿 |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| └─ color | string | 标签颜色 |

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
    "sha": "abc123"
  },
  "base": {
    "label": "main",
    "ref": "main",
    "sha": "def456"
  },
  "created_at": "2024-01-01T00:00:00+08:00",
  "updated_at": "2024-01-01T00:00:00+08:00",
  "merged_at": null,
  "closed_at": null,
  "mergeable": true,
  "merged": false,
  "closed": false,
  "draft": false,
  "labels": [
    {
      "id": 1,
      "name": "enhancement",
      "color": "#84b6eb"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "新增功能",
    "head": "feature-branch",
    "base": "main",
    "body": "这是一个新增功能的PR"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "title": "新增功能",
    "head": "feature-branch",
    "base": "main",
    "body": "这是一个新增功能的PR"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
