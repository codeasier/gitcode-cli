# 指派用户审查 Pull Request

指派用户审查 Pull Request

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/pulls/:number/assignees`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-assignees

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
| assignees | string | 是 | 用户的个人空间地址, 以逗号分隔 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Pull Request ID |
| iid | integer | Pull Request序号 |
| number | integer | Pull Request编号 |
| title | string | Pull Request标题 |
| state | string | Pull Request状态 |
| assignees | array | 审查人列表 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |

### 响应示例

```json
{
  "id": 100,
  "iid": 1,
  "number": 1,
  "title": "新增功能",
  "state": "open",
  "assignees": [
    {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/assignees?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "assignees": "user1,user2"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/assignees"
params = {"access_token": "YOUR_TOKEN"}
data = {"assignees": "user1,user2"}

response = requests.post(url, params=params, json=data)
print(response.json())
```
