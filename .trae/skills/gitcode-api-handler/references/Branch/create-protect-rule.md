# 新建保护分支规则

为指定仓库创建一个新的保护分支规则。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/branches/setting/new`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-branches-setting-new

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体 (application/json)

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| wildcard | string | 是 | 分支名称模式（支持通配符，如 `release-*`） |
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
  "wildcard": "release-*",
  "pusher": "user1,user2",
  "merger": "user1"
}
```

### 响应示例

```json
{
  "id": 1,
  "wildcard": "release-*",
  "pusher": "user1,user2",
  "merger": "user1",
  "created_at": "2024-01-01T12:00:00.000+08:00",
  "updated_at": "2024-01-01T12:00:00.000+08:00"
}
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/branches/setting/new?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "wildcard": "release-*",
    "pusher": "user1,user2",
    "merger": "user1"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/branches/setting/new"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "wildcard": "release-*",
    "pusher": "user1,user2",
    "merger": "user1"
}

response = requests.put(url, params=params, json=data)
print(response.json())
```

## 注意事项

- 需要仓库的管理员权限
- `wildcard` 支持通配符，如 `release-*` 可以匹配所有以 `release-` 开头的分支
- `pusher` 和 `merger` 为空表示没有人有权限，只有管理员可以操作
