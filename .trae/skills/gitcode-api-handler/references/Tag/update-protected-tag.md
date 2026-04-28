# 修改项目保护tag

更新指定仓库的一个保护标签规则。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/protected_tags`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-protected-tags

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

### 请求体

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 是 | 标签名称（支持通配符，如 `v*` 或 `release-*`） |
| create_access_level | integer | 是 | 允许创建的访问级别 |

**访问级别说明：**

| 值 | 说明 |
|----|------|
| 0 | 不允许任何人 |
| 30 | 开发者、维护者、管理员 |
| 40 | 维护者、管理员 |

## 响应

### 响应结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| name | string | 保护标签名称 |
| create_access_level | integer | 允许创建的访问级别 |
| create_access_level_desc | string | 访问级别描述 |

### 响应示例

```json
{
  "name": "v*",
  "create_access_level": 30,
  "create_access_level_desc": "开发者、维护者、管理员"
}
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/protected_tags?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "v*",
    "create_access_level": 30
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/protected_tags"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "name": "v*",
    "create_access_level": 30
}

response = requests.put(url, params=params, json=data)
print(response.json())
```
