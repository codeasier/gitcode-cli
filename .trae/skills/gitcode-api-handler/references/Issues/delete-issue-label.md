# 删除Issue标签

删除指定 Issue 的某个标签

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/issues/:number/labels/:name`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-issues-number-labels-name

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Issue编号 |
| name | string | 是 | 标签名称 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

成功删除后返回空响应

### 响应示例

```json
{}
```

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/labels/:name?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/labels/bug"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.delete(url, headers=headers, params=params)
print(response.status_code)
```
