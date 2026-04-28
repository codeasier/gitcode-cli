# 取消用户评审Pull Request

取消用户评审Pull Request

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/pulls/:number/reviewers`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-number-approval-reviewers

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | 第几个PR，即本仓库PR的序数。对应iid |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| reviewers | string | 是 | 用户的个人空间地址, 以逗号分隔 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 用户ID |
| login | string | 账号 |
| name | string | 昵称 |
| avatar_url | string | 头像 |
| object_id | object | ID |

### 响应示例

```json
[
  {
    "id": 123,
    "login": "username",
    "name": "用户昵称",
    "avatar_url": "https://gitcode.com/avatar.png",
    "object_id": {
      "id": "123"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/reviewers?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "reviewers": "user1,user2"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/reviewers"
params = {"access_token": "YOUR_TOKEN"}
data = {"reviewers": "user1,user2"}

response = requests.delete(url, params=params, json=data)
print(response.json())
```
