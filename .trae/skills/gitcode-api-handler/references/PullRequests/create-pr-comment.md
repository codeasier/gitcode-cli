# 提交pull request 评论

提交pull request 评论

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/pulls/:number/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-comments

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| body | string | 是 | 评论内容 |
| path | string | 否 | 文件的相对路径 |
| position | integer | 否 | 代码所在行数 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | string | 评论ID |
| body | string | 评论内容 |

### 响应示例

```json
{
  "id": "97219c08d421e55cfa841deca16a30f5d7269e10",
  "body": "这是一条评论"
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "这是一条评论",
    "path": "src/main.py",
    "position": 10
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/comments"
params = {"access_token": "YOUR_TOKEN"}
data = {
    "body": "这是一条评论",
    "path": "src/main.py",
    "position": 10
}

response = requests.post(url, params=params, json=data)
print(response.json())
```
