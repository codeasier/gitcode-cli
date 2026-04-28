# 更新保护分支规则

更新指定仓库中的一个保护分支规则。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/branches/:wildcard/setting`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-branches-wildcard-setting

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| wildcard | string | 是 | 分支名称模式（需要进行URL编码） |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体 (application/json)

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| pusher | string | 否 | 允许推送的用户（用户名，多个用逗号分隔） |
| merger | string | 否 | 允许合并的用户（用户名，多个用逗号分隔） |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | 保护规则id |
| wildcard | string | 分支名称模式 |
| pusher | string | 允许推送的用户 |
| merger | string | 允许合并的用户 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 请求示例

```json
{
  "pusher": "user1,user2,user3",
  "merger": "user1,user2"
}
```

### 响应示例

```json
{
  "id": 1,
  "wildcard": "release-*",
  "pusher": "user1,user2,user3",
  "merger": "user1,user2",
  "created_at": "2024-01-01T12:00:00.000+08:00",
  "updated_at": "2024-01-02T14:30:00.000+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/branches/:wildcard/setting?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "pusher": "user1,user2,user3",
    "merger": "user1,user2"
  }'
```

### Python

```python
import requests
from urllib.parse import quote

wildcard = "release-*"
encoded_wildcard = quote(wildcard, safe='')
url = f"https://api.gitcode.com/api/v5/repos/owner/repo/branches/{encoded_wildcard}/setting"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "pusher": "user1,user2,user3",
    "merger": "user1,user2"
}

response = requests.put(url, params=params, json=data)
print(response.json())
```

## 注意事项

- 需要仓库的管理员权限
- `wildcard` 参数需要进行 URL 编码，特别是包含特殊字符（如 `*`）时
- 更新操作会覆盖原有的 `pusher` 和 `merger` 设置
