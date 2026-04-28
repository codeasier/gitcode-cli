# 创建一个仓库的Tag

在指定仓库中创建一个新标签。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/tags`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-tags

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

### 请求体

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| refs | string | 是 | 创建标签所基于的分支或commit SHA |
| tag_name | string | 是 | 标签名称 |
| tag_message | string | 否 | 标签说明信息（创建轻量标签时不需要） |

## 响应

### 响应结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| name | string | 标签名称 |
| message | string | 标签说明信息 |
| commit | object | 提交信息对象 |
| └─ id | string | 提交记录id（SHA值） |
| └─ short_id | string | 提交短id |
| └─ title | string | 提交标题 |
| └─ message | string | 提交信息 |
| └─ author_name | string | 作者名称 |
| └─ author_email | string | 作者邮箱 |
| └─ authored_date | string | 作者提交时间 |
| └─ committer_name | string | 提交者名称 |
| └─ committer_email | string | 提交者邮箱 |
| └─ committed_date | string | 提交时间 |
| └─ created_at | string | 创建时间 |

### 响应示例

```json
{
  "name": "v1.0.0",
  "message": "Release version 1.0.0",
  "commit": {
    "id": "2912b8f2328e798f7d544272ffaebfccccb598ab",
    "short_id": "2912b8f2",
    "title": "Release v1.0.0",
    "message": "Release v1.0.0",
    "author_name": "test",
    "author_email": "test@example.com",
    "authored_date": "2024-01-01T12:00:00.000+08:00",
    "committer_name": "test",
    "committer_email": "test@example.com",
    "committed_date": "2024-01-01T12:00:00.000+08:00",
    "created_at": "2024-01-01T12:00:00.000+08:00"
  }
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/tags?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "refs": "master",
    "tag_name": "v1.0.0",
    "tag_message": "Release version 1.0.0"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/tags"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "refs": "master",
    "tag_name": "v1.0.0",
    "tag_message": "Release version 1.0.0"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
