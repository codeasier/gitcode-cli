# 获取commit的patch

获取指定提交的patch信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/commit/:sha/patch`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-commits-sha-patch

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

返回patch格式的文本内容,可用于应用补丁。

### 响应示例

```patch
From abc123def456 Mon Sep 17 00:00:00 2001
From: Test User <test@example.com>
Date: Mon, 1 Jan 2024 12:00:00 +0800
Subject: [PATCH] Update README.md

---
 README.md | 10 ++++++++--
 1 file changed, 8 insertions(+), 2 deletions(-)

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
-- 
2.25.1
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/commit/:sha/patch?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/commit/sha/patch"
params = {
}

response = requests.get(url, params=params)
print(response.text)
```
