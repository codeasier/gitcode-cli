# 获取项目Pull Request列表

获取项目Pull Request列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls

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
| state | string | 否 | Pull Request状态，all：所有，open：开启，closed：关闭，merged：合并 |
| sort | string | 否 | 排序字段，创建时间：created，更新时间：updated。默认按创建时间 |
| direction | string | 否 | 升序：asc，降序：desc |
| page | integer | 否 | 当前的页码:默认为 1 |
| per_page | integer | 否 | 每页的数量，最大为 100，默认 20 |
| base | string | 否 | 目标分支 |
| author | string | 否 | pull request作者 |
| search | string | 否 | 根据 title、description 模糊查询 |
| created_after | string | 否 | 返回在指定时间之后创建的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| created_before | string | 否 | 返回在指定时间之前创建的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| updated_before | string | 否 | 返回在指定时间之前更新的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| updated_after | string | 否 | 返回在指定时间之后更新的合并请求,要求时间格式为 ISO 8601 例如：2024-11-20T13:00:21+08:00 |
| labels | string | 否 | 根据指定的label名称进行筛选，多个使用英文逗号相隔 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| number | integer | PR序号 |
| integer | integer | - |
| html_url | string | PR页面URL |
| url | string | API URL |
| close_related_issue | integer | 关联issue |
| prune_branch | boolean | 是否删除源分支 |
| draft | boolean | 是否为草稿 |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| assignees | array | 审查人列表 |
| testers | array | 测试人列表 |
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
| id | integer | PR ID |
| iid | integer | PR序号 |
| project_id | integer | 项目ID |
| title | string | PR标题 |
| body | string | PR描述 |
| state | string | PR状态 |
| assignees_number | integer | 审查人数量 |
| testers_number | integer | 测试人数量 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |
| target_branch | string | 目标分支 |
| source_branch | string | 源分支 |
| source_project_id | integer | 源项目ID |
| force_remove_source_branch | boolean | 是否强制删除源分支 |
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
| can_merge_check | boolean | 是否可合并检查 |
| mergeable | boolean | 是否可合并 |
| locked | boolean | 是否锁定 |
| closed_by | object | 关闭者信息 |
| visibility_reason | string | 可见性，public：公开可见，other：仅项目成员可见 |
| merged_by | object | 合并者信息 |

### 响应示例

```json
[
  {
    "number": 1,
    "html_url": "https://gitcode.com/owner/repo/pulls/1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1",
    "close_related_issue": 0,
    "prune_branch": false,
    "draft": false,
    "labels": [
      {
        "id": 1,
        "name": "bug"
      }
    ],
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
    "id": 100,
    "iid": 1,
    "project_id": 1,
    "title": "修复bug",
    "body": "这是一个修复bug的PR",
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
    "force_remove_source_branch": false,
    "web_url": "https://gitcode.com/owner/repo/pulls/1",
    "merge_request_type": "normal",
    "review_mode": "normal",
    "added_lines": 10,
    "removed_lines": 5,
    "diff_refs": {},
    "notes": 0,
    "pipeline_status": "success",
    "pipeline_status_with_code_quality": "success",
    "source_git_url": "https://gitcode.com/owner/repo.git",
    "can_merge_check": true,
    "mergeable": true,
    "locked": false,
    "closed_by": null,
    "visibility_reason": "public",
    "merged_by": null
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls"
params = {
    "access_token": "YOUR_TOKEN",
    "state": "open",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
