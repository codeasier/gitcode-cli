# 指派用户测试 Pull Request

指派用户测试 Pull Request

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/pulls/:number/testers`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-testers

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
| testers | string | 是 | 用户的个人空间地址, 以逗号分隔 |
| add | boolean | 否 | 是否新增测试人，为true会新增测试人，false会覆盖更新测试人，默认false |

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
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/testers?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "testers": "user1,user2",
    "add": true
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/testers"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "testers": "user1,user2",
    "add": True
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
