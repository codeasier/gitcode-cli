# 列出 star 了仓库的用户

获取 star(收藏)了指定仓库的用户列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/stargazers`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-stargazers

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
| page | integer | 否 | 页码,默认为1 |
| per_page | integer | 否 | 每页数量,默认为20,最大为100 |

## 响应字段

返回数组,每个元素包含:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 用户ID |
| login | string | 用户名 |
| name | string | 用户昵称 |
| avatar_url | string | 用户头像URL |
| html_url | string | 用户主页URL |
| type | string | 用户类型:User |
| site_admin | boolean | 是否为站点管理员 |
| created_at | string | 账号创建时间 |
| updated_at | string | 账号更新时间 |
| followers | integer | 粉丝数 |
| following | integer | 关注数 |
| public_repos | integer | 公开仓库数 |
| public_gists | integer | 公开Gist数 |
| starred_at | string | Star时间 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/stargazers?access_token=YOUR_TOKEN&per_page=10"
```

## 响应示例

```json
[
  {
    "id": 12345,
    "login": "username1",
    "name": "User One",
    "avatar_url": "https://gitcode.com/avatar1.png",
    "html_url": "https://gitcode.com/username1",
    "type": "User",
    "site_admin": false,
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "followers": 100,
    "following": 50,
    "public_repos": 20,
    "public_gists": 5,
    "starred_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": 67890,
    "login": "username2",
    "name": "User Two",
    "avatar_url": "https://gitcode.com/avatar2.png",
    "html_url": "https://gitcode.com/username2",
    "type": "User",
    "site_admin": false,
    "created_at": "2023-06-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "followers": 200,
    "following": 80,
    "public_repos": 30,
    "public_gists": 10,
    "starred_at": "2024-01-16T14:20:00Z"
  }
]
```

## 相关接口

- [列出watch了仓库的用户](get-subscribers.md)
- [查看仓库的Forks](get-forks.md)
- [获取仓库贡献者](get-contributors.md)
