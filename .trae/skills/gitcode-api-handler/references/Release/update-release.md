# 更新仓库Release

更新指定仓库的 Release 版本信息。

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/releases/:tag`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-releases-tag

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| tag | string | 是 | Tag 名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体 (application/json)

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 否 | Release 名称 |
| body | string | 否 | Release 描述信息 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | Release ID |
| tag_name | string | Tag 名称 |
| target_commitish | string | 分支名称或commit SHA |
| prerelease | boolean | 是否为预发布版本 |
| name | string | Release 名称 |
| body | string | Release 描述信息 |
| author | object | 创建者信息 |
| └─ id | string | 用户ID |
| └─ login | string | 用户登录名 |
| └─ name | string | 用户昵称 |
| └─ avatar_url | string | 用户头像URL |
| created_at | string | 创建时间 |
| assets | array | 附件列表 |
| └─ id | integer | 附件ID |
| └─ name | string | 附件名称 |
| └─ content_type | string | 文件类型 |
| └─ size | integer | 文件大小(字节) |
| └─ download_count | integer | 下载次数 |
| └─ browser_download_url | string | 下载地址 |

### 请求示例

```json
{
  "name": "Version 1.0.1",
  "body": "修复了一些已知问题"
}
```

### 响应示例

```json
{
  "id": 12345,
  "tag_name": "v1.0.0",
  "target_commitish": "master",
  "prerelease": false,
  "name": "Version 1.0.1",
  "body": "修复了一些已知问题",
  "author": {
    "id": "user123",
    "login": "developer",
    "name": "开发者",
    "avatar_url": "https://gitcode.com/avatar/user123.png"
  },
  "created_at": "2024-01-15T10:30:00.000+08:00",
  "assets": [
    {
      "id": 1,
      "name": "app-v1.0.0.zip",
      "content_type": "application/zip",
      "size": 1048576,
      "download_count": 150,
      "browser_download_url": "https://gitcode.com/api/v5/repos/owner/repo/releases/assets/1"
    }
  ]
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/releases/:tag?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Version 1.0.1",
    "body": "修复了一些已知问题"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/releases/tag_name"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "name": "Version 1.0.1",
    "body": "修复了一些已知问题"
}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
