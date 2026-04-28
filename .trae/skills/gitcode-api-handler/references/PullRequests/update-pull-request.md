# 更新Pull Request信息

更新Pull Request信息

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/pulls/:number`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-number

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| title | string | 否 | Pull Request标题 |
| body | string | 否 | Pull Request描述 |
| state | string | 否 | Pull Request状态(open/closed) |
| milestone_number | integer | 否 | 里程碑编号 |
| labels | string | 否 | 标签名称，多个用逗号分隔 |
| draft | boolean | 否 | 是否为草稿 |
| close_related_issue | boolean | 否 | 是否关闭关联的Issue |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Pull Request ID |
| iid | integer | Pull Request序号 |
| number | integer | Pull Request编号 |
| title | string | Pull Request标题 |
| body | string | Pull Request描述 |
| state | string | Pull Request状态 |
| html_url | string | Pull Request页面URL |
| url | string | API URL |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| merged_at | string | 合并时间 |
| closed_at | string | 关闭时间 |
| draft | boolean | 是否为草稿 |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| └─ color | string | 标签颜色 |

### 响应示例

```json
{
  "id": 100,
  "iid": 1,
  "number": 1,
  "title": "更新后的标题",
  "body": "更新后的描述",
  "state": "open",
  "html_url": "https://gitcode.com/owner/repo/pulls/1",
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/pulls/1",
  "user": {
    "id": "123",
    "login": "username",
    "name": "用户昵称",
    "avatar_url": "https://gitcode.com/avatar.png"
  },
  "created_at": "2024-01-01T00:00:00+08:00",
  "updated_at": "2024-01-02T00:00:00+08:00",
  "merged_at": null,
  "closed_at": null,
  "draft": false,
  "labels": [
    {
      "id": 1,
      "name": "enhancement",
      "color": "#84b6eb"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "更新后的标题",
    "body": "更新后的描述",
    "state": "open"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "title": "更新后的标题",
    "body": "更新后的描述",
    "state": "open"
}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
