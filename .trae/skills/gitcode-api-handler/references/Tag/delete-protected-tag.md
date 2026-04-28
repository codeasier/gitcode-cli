# 删除项目保护tag

删除指定仓库中的一个保护标签规则。

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/protected_tags/:tag_name`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-protected-tags-tag-name

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

成功删除后返回 204 No Content 状态码。

### 响应示例

```
HTTP/1.1 204 No Content
```

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/protected_tags/:tag_name?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/protected_tags/v*"
params = {"access_token": "YOUR_TOKEN"}

response = requests.delete(url, params=params)
print(f"Status Code: {response.status_code}")
```
