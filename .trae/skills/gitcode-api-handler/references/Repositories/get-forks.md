# 查看仓库的Forks

获取指定仓库的所有Fork列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/forks`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-forks

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
| sort | string | 否 | 排序方式:newest(最新)、oldest(最旧)、stargazers(Star数),默认为newest |
| page | integer | 否 | 页码,默认为1 |
| per_page | integer | 否 | 每页数量,默认为20,最大为100 |

## 响应字段

返回数组,每个元素包含:

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
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/forks?access_token=YOUR_TOKEN&sort=stargazers&per_page=10"
```

## 响应示例

```json
[
  {
    "id": 123456,
    "name": "forked-repo",
    "path": "forked-repo",
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
      "login": "fork-user",
      "avatar_url": "https://gitcode.com/avatar.png"
    },
    "html_url": "https://gitcode.com/fork-user/forked-repo",
    "ssh_url": "git@gitcode.com:fork-user/forked-repo.git",
    "clone_url": "https://gitcode.com/fork-user/forked-repo.git",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z",
    "stargazers_count": 10,
    "watchers_count": 5,
    "forks_count": 2,
    "open_issues_count": 3,
    "default_branch": "master"
  }
]
```

## 相关接口

- [Fork一个仓库](fork-repo.md)
- [获取仓库详情](get-repo-settings.md)
- [列出star了仓库的用户](get-stargazers.md)
