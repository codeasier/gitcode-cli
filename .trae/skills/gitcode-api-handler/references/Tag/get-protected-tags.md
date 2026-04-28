# 列出项目保护tags

获取指定仓库的所有保护标签列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/protected_tags`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-protected-tags

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
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

## 响应

### 响应结构 (array)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| name | string | 保护标签名称 |
| create_access_level | integer | 允许创建的访问级别 |
| create_access_level_desc | string | 访问级别描述 |

### 响应示例

```json
[
  {
    "name": "v*",
    "create_access_level": 40,
    "create_access_level_desc": "维护者、管理员"
  },
  {
    "name": "release-*",
    "create_access_level": 30,
    "create_access_level_desc": "开发者、维护者、管理员"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/protected_tags?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/protected_tags"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
