# 合并Pull Request

合并Pull Request

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/pulls/:number/merge`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-merge

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| merge_method | string | 否 | 合并方法：merge(默认)、squash、rebase |
| title | string | 否 | 合并提交标题 |
| description | string | 否 | 合并提交描述 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| sha | string | 合并提交的SHA |
| merged | boolean | 是否已合并 |
| message | string | 合并消息 |

### 响应示例

```json
{
  "sha": "abc123def456",
  "merged": true,
  "message": "Pull Request successfully merged"
}
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/merge?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "merge_method": "merge",
    "title": "合并PR",
    "description": "合并描述"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/merge"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "merge_method": "merge",
    "title": "合并PR",
    "description": "合并描述"
}

response = requests.put(url, params=params, json=data)
print(response.json())
```
