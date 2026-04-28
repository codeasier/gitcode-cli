# 设置Issue关联的分支

为指定的 Issue 设置关联的分支

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/issues/:number/related_branches`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-issues-number-related-branches

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | string | 是 | issue编号 |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| branch_names | array | 是 | 分支名列表 |

## 响应

### 响应结构

返回分支名称字符串数组

### 响应示例

```json
[
  "feature/new-feature",
  "bugfix/issue-123"
]
```

## 请求示例

### cURL

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/issues/:number/related_branches?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "branch_names": ["feature/new-feature", "bugfix/issue-123"]
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1/related_branches"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}
data = {
    "branch_names": ["feature/new-feature", "bugfix/issue-123"]
}

response = requests.put(url, headers=headers, params=params, json=data)
print(response.json())
```
