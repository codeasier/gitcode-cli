# 获取某个issue下的操作日志

获取指定 Issue 的所有操作日志

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/issues/:number/operate_logs`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-issues-number-operate-logs

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| repo | string | 是 | 仓库路径(path) |

## 响应

### 响应结构

返回操作日志对象数组

### 响应示例

```json
[
  {
    "id": 1,
    "action": "created",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户名"
    },
    "created_at": "2024-01-01T10:00:00+08:00",
    "details": "创建了Issue"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/issues/:number/operate_logs?access_token=YOUR_TOKEN&repo=my-repo" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/issues/1/operate_logs"
params = {
    "access_token": "YOUR_TOKEN",
    "repo": "my-repo"
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
