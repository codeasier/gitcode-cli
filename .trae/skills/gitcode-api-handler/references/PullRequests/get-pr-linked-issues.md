# 获取pr关联的issue

获取pr关联的issue

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-issues

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

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Issue ID |
| iid | integer | Issue序号 |
| number | string | Issue编号 |
| title | string | Issue标题 |
| body | string | Issue描述 |
| state | string | Issue状态 |
| html_url | string | Issue页面URL |
| url | string | API URL |
| user | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| labels | array | 标签列表 |
| └─ id | integer | 标签ID |
| └─ name | string | 标签名称 |
| └─ color | string | 标签颜色 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| closed_at | string | 关闭时间 |

### 响应示例

```json
[
  {
    "id": 1,
    "iid": 1,
    "number": "1",
    "title": "修复bug",
    "body": "这是一个bug修复",
    "state": "open",
    "html_url": "https://gitcode.com/owner/repo/issues/1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    },
    "labels": [
      {
        "id": 1,
        "name": "bug",
        "color": "#d73a4a"
      }
    ],
    "created_at": "2024-01-01T00:00:00+08:00",
    "updated_at": "2024-01-01T00:00:00+08:00",
    "closed_at": null
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/issues?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/issues"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
