# Pull Request Commit文件列表

Pull Request Commit文件列表

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/files`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-files

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

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| sha | string | 文件SHA |
| filename | string | 文件名 |
| status | string | 文件状态(added/modified/removed/renamed) |
| additions | integer | 新增行数 |
| deletions | integer | 删除行数 |
| changes | integer | 变更行数 |
| blob_url | string | Blob URL |
| raw_url | string | Raw URL |
| contents_url | string | 内容URL |
| patch | string | 补丁内容 |
| previous_filename | string | 之前的文件名(重命名时) |

### 响应示例

```json
[
  {
    "sha": "abc123def456",
    "filename": "src/main.py",
    "status": "modified",
    "additions": 10,
    "deletions": 5,
    "changes": 15,
    "blob_url": "https://gitcode.com/owner/repo/blob/abc123/src/main.py",
    "raw_url": "https://gitcode.com/owner/repo/raw/abc123/src/main.py",
    "contents_url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/src/main.py",
    "patch": "@@ -1,5 +1,10 @@\n old line\n+new line"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/files?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/files"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
