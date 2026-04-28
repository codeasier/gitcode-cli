# 获取commit的diff

获取指定提交的diff信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/commit/:sha/diff`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-commits-sha-diff

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| sha | string | 是 | commit的id(SHA值) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构 (string)

返回diff格式的文本内容,包含文件变更的详细信息。

### 响应示例

```diff
diff --git a/README.md b/README.md
index abc123..def456 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,10 @@
 # Project Title
-Old description
+New description with more details
+
+## Features
+- Feature 1
+- Feature 2
+
+## Installation
+Instructions here
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/commit/:sha/diff?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/commit/sha/diff"
params = {
}

response = requests.get(url, params=params)
print(response.text)
```
