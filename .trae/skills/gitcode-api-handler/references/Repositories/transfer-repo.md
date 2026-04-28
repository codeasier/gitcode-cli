# 仓库转移

将仓库转移给其他用户或组织。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/transfer`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-transfer

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| new_owner | string | 是 | 新所有者的用户名或组织名 |
| new_name | string | 否 | 转移后的新仓库名称,默认保持原名 |
| team_ids | array | 否 | 团队ID数组,转移到的组织时可以指定团队权限 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 仓库ID |
| name | string | 仓库名称 |
| path | string | 仓库路径 |
| description | string | 仓库描述 |
| private | boolean | 是否为私有仓库 |
| public | boolean | 是否为公开仓库 |
| owner | object | 仓库所有者信息 |
| └─ id | integer | 所有者ID |
| └─ login | string | 所有者用户名 |
| └─ type | string | 所有者类型:User或Organization |
| └─ avatar_url | string | 所有者头像URL |
| html_url | string | 仓库网页URL |
| ssh_url | string | SSH克隆URL |
| clone_url | string | HTTPS克隆URL |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| stargazers_count | integer | Star数量 |
| watchers_count | integer | Watch数量 |
| forks_count | integer | Fork数量 |
| open_issues_count | integer | 未关闭的Issue数量 |
| default_branch | string | 默认分支 |

## 请求示例

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/transfer?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_owner": "target-organization",
    "new_name": "new-repo-name",
    "team_ids": [1, 2, 3]
  }'
```

## 响应示例

```json
{
  "id": 123456,
  "name": "new-repo-name",
  "path": "new-repo-name",
  "description": "Repository description",
  "private": false,
  "public": true,
  "owner": {
    "id": 789,
    "login": "target-organization",
    "type": "Organization",
    "avatar_url": "https://gitcode.com/avatar.png"
  },
  "html_url": "https://gitcode.com/target-organization/new-repo-name",
  "ssh_url": "git@gitcode.com:target-organization/new-repo-name.git",
  "clone_url": "https://gitcode.com/target-organization/new-repo-name.git",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-15T12:00:00Z",
  "stargazers_count": 100,
  "watchers_count": 50,
  "forks_count": 20,
  "open_issues_count": 10,
  "default_branch": "main"
}
```

## 相关接口

- [转移仓(组织)](org-transfer-repo.md)
- [Fork一个仓库](fork-repo.md)
- [删除仓库](delete-repo.md)
