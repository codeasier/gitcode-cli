# Pull Request关联issue

Pull Request关联issue

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/pulls/:number/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-linked-issues

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
| issue_numbers | array | 是 | Issue编号数组 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Issue ID |
| iid | integer | Issue序号 |
| number | string | Issue编号 |
| title | string | Issue标题 |
| state | string | Issue状态 |
| html_url | string | Issue页面URL |

### 响应示例

```json
[
  {
    "id": 1,
    "iid": 1,
    "number": "1",
    "title": "修复bug",
    "state": "open",
    "html_url": "https://gitcode.com/owner/repo/issues/1"
  }
]
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/issues?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '[1, 2]'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/issues"
params = {"access_token": "YOUR_TOKEN"}
data = [1, 2]

response = requests.post(url, params=params, json=data)
print(response.json())
```
