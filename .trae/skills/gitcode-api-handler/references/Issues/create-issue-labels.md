# 创建Issue标签

为指定的 Issue 创建标签

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/issues/:number/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-issues-number-labels

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | Issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| - | array | 是 | 标签名称数组 |

## 响应

### 响应结构

返回标签对象数组

### 响应示例

```json
[
  {
    "id": 1,
    "name": "bug",
    "color": "ff0000",
    "description": "Bug标签"
  }
]
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/labels?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '["bug", "high-priority"]'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/labels"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}
data = ["bug", "high-priority"]

response = requests.post(url, headers=headers, params=params, json=data)
print(response.json())
```
