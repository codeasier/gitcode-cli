# 获取仓库所有任务标签

获取指定仓库的所有标签列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-labels

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
| id | integer | 标签ID |
| name | string | 标签名称 |
| color | string | 标签颜色（十六进制） |
| description | string | 标签描述 |
| default | boolean | 是否为默认标签 |

### 响应示例

```json
[
  {
    "id": 1,
    "name": "bug",
    "color": "d73a4a",
    "description": "Something isn't working",
    "default": true
  },
  {
    "id": 2,
    "name": "enhancement",
    "color": "a2eeef",
    "description": "New feature or request",
    "default": true
  },
  {
    "id": 3,
    "name": "documentation",
    "color": "0075ca",
    "description": "Improvements or additions to documentation",
    "default": false
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/labels?access_token=YOUR_TOKEN&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/labels"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
