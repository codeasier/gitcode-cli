# 获取issue的修改历史

获取指定 Issue 的所有修改历史记录

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/issues/:number/modify_history`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-issues-number-modify-history

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回修改历史对象数组

### 响应示例

```json
[
  {
    "id": "1",
    "field": "title",
    "old_value": "旧标题",
    "new_value": "新标题",
    "user": {
      "id": "123",
      "login": "username",
      "name": "用户名"
    },
    "created_at": "2024-01-01T10:00:00+08:00"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/modify_history?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/modify_history"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
