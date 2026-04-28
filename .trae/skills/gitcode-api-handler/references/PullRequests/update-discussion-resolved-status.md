# 修改检视意见解决状态

修改检视意见解决状态

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/pulls/:number/comments/:discussion_id`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-comments-discussions-id

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | 第几个PR，即本仓库PR的序数。对应iid |
| discussion_id | string | 是 | 讨论的ID（字符串类型 id） |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 否 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| resolved | boolean | 是 | 是否已解决 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 讨论ID |
| resolved | boolean | 是否已解决 |

### 响应示例

```json
{
  "id": "abc123",
  "resolved": true
}
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments/:discussion_id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "resolved": true
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments/:discussion_id"
params = {"access_token": "YOUR_TOKEN"}
data = {"resolved": True}

response = requests.put(url, params=params, json=data)
print(response.json())
```
