# 获取项目保护tag详情

获取指定仓库中某个保护标签规则的详细信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/protected_tags/:tag_name`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-protected-tags-tag-name

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| tag_name | string | 是 | 保护标签名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

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
  "create_access_level": 40,
  "create_access_level_desc": "维护者、管理员"
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/protected_tags/:tag_name?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/protected_tags/v*"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
