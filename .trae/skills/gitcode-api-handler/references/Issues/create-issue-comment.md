# 创建Issue评论

为指定的 Issue 创建评论

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/issues/:number/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-issues-number-comments

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| body | string | 是 | 评论内容 |

## 响应

### 响应结构

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
{
  "id": 271624,
  "body": "评论内容。",
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
      "id": 152134,
      "title": "",
      "nubmer": 1
    }
  },
  "created_at": null,
  "updated_at": null
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/comments?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "这是一条评论内容"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/comments"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}
data = {
    "body": "这是一条评论内容"
}

response = requests.post(url, headers=headers, params=params, json=data)
print(response.json())
```
