# 删除保护分支规则

删除指定仓库中的一个保护分支规则。

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/branches/:wildcard/setting`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-branches-wildcard-setting

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

## 响应

成功时返回 HTTP 204 No Content（无响应体）

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/branches/:wildcard/setting?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests
from urllib.parse import quote

wildcard = "release-*"
encoded_wildcard = quote(wildcard, safe='')
url = f"https://api.gitcode.com/api/v5/repos/owner/repo/branches/{encoded_wildcard}/setting"
params = {"access_token": "YOUR_TOKEN"}

response = requests.delete(url, params=params)
print(response.status_code)  # 204
```

## 注意事项

- 需要仓库的管理员权限
- `wildcard` 参数需要进行 URL 编码，特别是包含特殊字符（如 `*`）时
- 删除操作不可逆，请谨慎使用
