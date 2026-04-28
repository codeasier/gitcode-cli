# 获取仓库所有 Issue 评论

获取指定仓库的所有 Issue 评论列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-comments

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| sort | string | 否 | Either created or updated. Default: created |
| direction | string | 否 | Either asc or desc. Ignored without the sort parameter. |
| since | string | 否 | Only comments updated at or after this time are returned. This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量,最大为 100,默认 20 |

## 响应

### 响应结构

返回评论对象数组,每个对象包含以下字段:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | integer | 评论ID |
| body | string | 评论内容 |
| user | object | 评论用户信息 |
| user.avatar_url | string | 用户头像URL |
| user.html_url | string | 用户主页URL |
| user.id | string | 用户ID |
| user.login | string | 用户登录名 |
| user.name | string | 用户名称 |
| target | object | 目标对象 |
| target.issue | object | Issue信息 |
| target.issue.id | integer | Issue ID |
| target.issue.title | string | Issue标题 |
| target.issue.nubmer | integer | Issue编号 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
[
  {
    "id": 272201,
    "body": "daetete",
    "user": {
      "avatar_url": "https://gitcode-img.obs.cn-south-1.myhuaweicloud.com:443/fa/fe/f32a9fecc53e890afbd48fd098b0f6c5f20f062581400c76c85e5baab3f0d5b2.png",
      "events_url": null,
      "followers_url": null,
      "following_url": null,
      "gists_url": null,
      "html_url": "https://test.gitcode.net/dengmengmian",
      "id": "661ce4eab470b1430d456154",
      "login": "dengmengmian",
      "member_role": null,
      "name": "麻凡_",
      "organizations_url": null,
      "received_events_url": null,
      "remark": null,
      "repos_url": null,
      "starred_url": null,
      "subscriptions_url": null,
      "type": null,
      "url": null
    },
    "target": {
      "issue": {
        "id": 152642,
        "title": "半月据",
        "nubmer": 15
      }
    },
    "created_at": "2024-04-20T15:20:30.104+08:00",
    "updated_at": null
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/comments?access_token=YOUR_TOKEN&sort=created&direction=desc" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/comments"
params = {
    "access_token": "YOUR_TOKEN",
    "sort": "created",
    "direction": "desc"
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
