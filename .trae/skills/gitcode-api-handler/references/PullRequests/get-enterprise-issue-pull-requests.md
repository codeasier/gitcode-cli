# 获取企业 issue 关联的 Pull Requests

获取企业 issue 关联的 Pull Requests

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issues/:number/pull_requests`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issues-number-pull-requests

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| enterprise | string | 是 | org(path/login) |
| number | integer | 是 | issue 全局 id |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| number | integer | Pull Request编号 |
| html_url | string | Pull Request页面URL |
| url | string | API URL |
| close_related_issue | integer | 关联issue |
| prune_branch | integer | 是否删除源分支 |
| draft | integer | 是否为草稿 |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| └─ color | string | 标签颜色 |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
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
| head | object | 源分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| base | object | 目标分支信息 |
| └─ label | string | 分支标签 |
| └─ ref | string | 分支名称 |
| └─ sha | string | 提交SHA |
| id | integer | Pull Request ID |
| iid | integer | Pull Request序号 |
| project_id | integer | 项目ID |
| title | string | Pull Request标题 |
| body | string | Pull Request描述 |
| state | string | Pull Request状态 |
| assignees_number | integer | 审查人数量 |
| testers_number | integer | 测试人数量 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |
| target_branch | string | 目标分支 |
| source_branch | string | 源分支 |
| source_project_id | integer | 源项目ID |
| force_remove_source_branch | integer | 是否强制删除源分支 |
| web_url | string | Web URL |
| merge_request_type | string | 合并请求类型 |
| review_mode | string | 审查模式 |
| added_lines | integer | 新增行数 |
| removed_lines | integer | 删除行数 |
| diff_refs | object | 差异引用 |
| notes | integer | 评论数 |
| pipeline_status | string | 流水线状态 |
| pipeline_status_with_code_quality | string | 包含代码质量的流水线状态 |
| source_git_url | string | 源Git URL |
| can_merge_check | integer | 是否可合并检查 |
| mergeable | integer | 是否可合并 |
| locked | integer | 是否锁定 |
| diff_url | string | Diff URL |
| patch_url | string | Patch URL |
| commits_url | string | Commits URL |
| comments_url | string | Comments URL |
| issue_url | string | Issue URL |

### 响应示例

```json
[
  {
    "number": 1,
    "html_url": "https://gitcode.com/owner/repo/pulls/1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1",
    "close_related_issue": 0,
    "prune_branch": 0,
    "draft": 0,
    "labels": [],
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    },
    "assignees": [],
    "testers": [],
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
    "id": 100,
    "iid": 1,
    "project_id": 1,
    "title": "新增功能",
    "body": "这是一个新增功能的PR",
    "state": "open",
    "assignees_number": 0,
    "testers_number": 0,
    "created_at": "2024-01-01T00:00:00+08:00",
    "updated_at": "2024-01-01T00:00:00+08:00",
    "merged_at": null,
    "closed_at": null,
    "target_branch": "main",
    "source_branch": "feature-branch",
    "source_project_id": 1,
    "force_remove_source_branch": 0,
    "web_url": "https://gitcode.com/owner/repo/pulls/1",
    "merge_request_type": "normal",
    "review_mode": "normal",
    "added_lines": 100,
    "removed_lines": 50,
    "diff_refs": {},
    "notes": 0,
    "pipeline_status": "success",
    "pipeline_status_with_code_quality": "success",
    "source_git_url": "https://gitcode.com/owner/repo.git",
    "can_merge_check": 1,
    "mergeable": 1,
    "locked": 0,
    "diff_url": "https://gitcode.com/owner/repo/pulls/1.diff",
    "patch_url": "https://gitcode.com/owner/repo/pulls/1.patch",
    "commits_url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1/commits",
    "comments_url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1/comments",
    "issue_url": "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues/:number/pull_requests?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues/:number/pull_requests"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
