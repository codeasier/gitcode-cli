# 获取仓库Issue某条评论

获取指定仓库中某条 Issue 评论的详细信息

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-comments-id

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | string | 是 | 评论 ID |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

| 字段 | 类型 | 描述 |
|------|------|------|
| id | integer | 评论ID |
| body | string | 评论内容 |
| comment_type | string | 评论类型 |
| user | object | 评论用户信息 |
| user.id | string | 用户ID |
| user.login | string | 用户登录名 |
| user.name | string | 用户名称 |
| user.type | string | 用户类型 |
| target | object | 目标对象 |
| target.issue | object | Issue信息 |
| target.issue.id | integer | Issue ID |
| target.issue.title | string | Issue标题 |
| target.issue.number | string | Issue编号 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
{
  "id": 1495484,
  "body": "测试 issue 评论",
  "comment_type": "DiscussionNote",
  "user": {
    "id": "268",
    "login": "dengmengmian",
    "name": "麻凡",
    "type": "User"
  },
  "target": {
    "issue": {
      "id": 494561,
      "title": "测试 issue 评论",
      "number": "494561"
    }
  },
  "created_at": "2024-10-08T19:52:19+08:00",
  "updated_at": "2024-10-08T19:52:19+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/comments/1495484"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
