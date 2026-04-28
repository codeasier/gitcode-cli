# 仓库归档

将仓库设置为归档状态或取消归档状态。

## 基本信息

- **方法**: PUT
- **路径**: `/org/:org/repo/:repo/status`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-org-org-repo-repo-status

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| org | string | 是 | 组织名称 |
| repo | string | 是 | 仓库路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| archived | boolean | 是 | 是否归档:true(归档)、false(取消归档) |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 仓库ID |
| name | string | 仓库名称 |
| path | string | 仓库路径 |
| description | string | 仓库描述 |
| private | boolean | 是否为私有仓库 |
| public | boolean | 是否为公开仓库 |
| archived | boolean | 是否已归档 |
| owner | object | 仓库所有者信息 |
| └─ id | integer | 所有者ID |
| └─ login | string | 所有者用户名 |
| └─ type | string | 所有者类型 |
| └─ avatar_url | string | 所有者头像URL |
| html_url | string | 仓库网页URL |
| ssh_url | string | SSH克隆URL |
| clone_url | string | HTTPS克隆URL |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| archived_at | string | 归档时间(已归档时返回) |
| stargazers_count | integer | Star数量 |
| watchers_count | integer | Watch数量 |
| forks_count | integer | Fork数量 |
| open_issues_count | integer | 未关闭的Issue数量 |
| default_branch | string | 默认分支 |

## 请求示例

### 归档仓库

```bash
curl -X PUT "https://api.gitcode.com/api/v5/org/:org/repo/:repo/status?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "archived": true
  }'
```

### 取消归档

```bash
curl -X PUT "https://api.gitcode.com/api/v5/org/:org/repo/:repo/status?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "archived": false
  }'
```

## 响应示例

```json
{
  "id": 123456,
  "name": "archived-repo",
  "path": "archived-repo",
  "description": "This repository has been archived",
  "private": false,
  "public": true,
  "archived": true,
  "owner": {
    "id": 789,
    "login": "my-organization",
    "type": "Organization",
    "avatar_url": "https://gitcode.com/avatar.png"
  },
  "html_url": "https://gitcode.com/my-organization/archived-repo",
  "ssh_url": "git@gitcode.com:my-organization/archived-repo.git",
  "clone_url": "https://gitcode.com/my-organization/archived-repo.git",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-15T12:00:00Z",
  "archived_at": "2024-01-15T12:00:00Z",
  "stargazers_count": 100,
  "watchers_count": 50,
  "forks_count": 20,
  "open_issues_count": 10,
  "default_branch": "main"
}
```

## 相关接口

- [仓库转移](transfer-repo.md)
- [删除仓库](delete-repo.md)
- [更新仓库设置](update-repo-settings.md)
