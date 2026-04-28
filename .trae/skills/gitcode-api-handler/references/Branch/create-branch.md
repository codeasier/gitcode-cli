# 创建分支

在指定仓库中创建一个新分支。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/branches`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-branches

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
| refs | string | 是 | 起点名称（源分支名），默认：master |
| branch_name | string | 是 | 新创建的分支名称 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| name | string | 分支名称 |
| commit | object | 提交信息对象 |
| commit.id | string | 提交记录id（SHA值） |
| commit.short_id | string | 提交短id |
| commit.title | string | 提交标题 |
| commit.message | string | 提交信息 |
| commit.author_name | string | 作者名称 |
| commit.author_email | string | 作者邮箱 |
| commit.authored_date | string | 作者提交时间 |
| commit.committer_name | string | 提交者名称 |
| commit.committer_email | string | 提交者邮箱 |
| commit.committed_date | string | 提交时间 |
| commit.created_at | string | 创建时间 |
| protected | integer | 是否受保护（0: 否, 1: 是） |

### 请求示例

```json
{
  "refs": "master",
  "branch_name": "feature-new"
}
```

### 响应示例

```json
{
  "name": "feature-new",
  "commit": {
    "id": "2912b8f2328e798f7d544272ffaebfccccb598ab",
    "short_id": "2912b8f2",
    "title": "Initial commit",
    "message": "Initial commit",
    "author_name": "test",
    "author_email": "test@example.com",
    "authored_date": "2024-01-01T12:00:00.000+08:00",
    "committer_name": "test",
    "committer_email": "test@example.com",
    "committed_date": "2024-01-01T12:00:00.000+08:00",
    "created_at": "2024-01-01T12:00:00.000+08:00"
  },
  "protected": 0
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/branches?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "refs": "master",
    "branch_name": "feature-new"
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/branches"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "refs": "master",
    "branch_name": "feature-new"
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
