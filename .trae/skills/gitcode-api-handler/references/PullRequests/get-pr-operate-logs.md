# 获取某个Pull Request的操作日志

获取某个Pull Request的操作日志

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/operate_logs`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-operate-logs

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
| id | integer | 日志ID |
| action | string | 操作类型 |
| created_at | string | 创建时间 |
| user | object | 操作用户信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| content | string | 操作内容 |

### 响应示例

```json
[
  {
    "id": 1,
    "action": "opened",
    "created_at": "2024-01-01T00:00:00+08:00",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户昵称",
      "avatar_url": "https://gitcode.com/avatar.png"
    },
    "content": "打开了Pull Request"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/operate_logs?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/operate_logs"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
