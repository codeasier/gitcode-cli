# 替换Issue所有标签

替换指定Issue的所有标签。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/issues/:number/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-issues-number-labels

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | Issue编号 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| labels | array | 是 | 标签名称数组 |
| └─ (element) | string | - | 标签名称 |

## 响应

### 响应结构 (array)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | 标签ID |
| name | string | 标签名称 |
| color | string | 标签颜色（十六进制） |
| description | string | 标签描述 |

### 响应示例

```json
[
  {
    "id": 1,
    "name": "bug",
    "color": "d73a4a",
    "description": "Something isn't working"
  },
  {
    "id": 2,
    "name": "priority",
    "color": "ff7b72",
    "description": "High priority issue"
  }
]
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/labels?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '["bug", "priority"]'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/labels"
params = {
}
data = ["bug", "priority"]

response = requests.put(url, params=params, json=data)
print(response.json())
```
