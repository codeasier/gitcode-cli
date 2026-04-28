# 创建仓库Release

创建一个新的仓库 Release 版本。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/releases`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-releases

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

### 请求体 (application/json)

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| tag_name | string | 是 | Tag 名称 |
| name | string | 否 | Release 名称 |
| body | string | 否 | Release 描述信息 |
| target_commitish | string | 否 | 分支名称或commit SHA，默认为默认分支 |

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
  "tag_name": "v1.0.0",
  "name": "Version 1.0.0",
  "body": "这是第一个正式版本发布",
  "target_commitish": "master"
}
```

### 响应示例

```json
{
  "id": 12345,
  "tag_name": "v1.0.0",
  "target_commitish": "master",
  "prerelease": false,
  "name": "Version 1.0.0",
  "body": "这是第一个正式版本发布",
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
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/releases?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "tag_name": "v1.0.0",
    "name": "Version 1.0.0",
    "body": "这是第一个正式版本发布",
    "target_commitish": "master"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/releases"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "tag_name": "v1.0.0",
    "name": "Version 1.0.0",
    "body": "这是第一个正式版本发布",
    "target_commitish": "master"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
