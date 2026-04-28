# Fork一个仓库

Fork指定仓库到当前用户的命名空间下。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/forks`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-forks

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
| organization | string | 否 | 组织名称,如果指定则fork到该组织下 |
| name | string | 否 | fork后的仓库名称,默认与原仓库相同 |
| default_branch_only | boolean | 否 | 是否仅fork默认分支,默认为false |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 仓库ID |
| name | string | 仓库名称 |
| path | string | 仓库路径 |
| description | string | 仓库描述 |
| private | boolean | 是否为私有仓库 |
| public | boolean | 是否为公开仓库 |
| fork | boolean | 是否为fork仓库 |
| forked_from | object | fork来源仓库信息 |
| └─ id | integer | 来源仓库ID |
| └─ name | string | 来源仓库名称 |
| └─ path | string | 来源仓库路径 |
| └─ owner | object | 来源仓库所有者信息 |
| owner | object | 仓库所有者信息 |
| └─ id | integer | 所有者ID |
| └─ login | string | 所有者用户名 |
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
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/forks?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-forked-repo",
    "default_branch_only": true
  }'
```

## 响应示例

```json
{
  "id": 123456,
  "name": "my-forked-repo",
  "path": "my-forked-repo",
  "description": "A forked repository",
  "private": false,
  "public": true,
  "fork": true,
  "forked_from": {
    "id": 654321,
    "name": "original-repo",
    "path": "original-repo",
    "owner": {
      "id": 111,
      "login": "original-owner"
    }
  },
  "owner": {
    "id": 222,
    "login": "my-username",
    "avatar_url": "https://gitcode.com/avatar.png"
  },
  "html_url": "https://gitcode.com/my-username/my-forked-repo",
  "ssh_url": "git@gitcode.com:my-username/my-forked-repo.git",
  "clone_url": "https://gitcode.com/my-username/my-forked-repo.git",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z",
  "stargazers_count": 0,
  "watchers_count": 0,
  "forks_count": 0,
  "open_issues_count": 0,
  "default_branch": "master"
}
```

## 相关接口

- [查看仓库的Forks](get-forks.md)
- [仓库转移](transfer-repo.md)
- [删除仓库](delete-repo.md)
