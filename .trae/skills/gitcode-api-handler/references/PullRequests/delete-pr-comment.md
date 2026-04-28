# 删除评论

删除评论

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/pulls/comments/:id`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-comments-id

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| id | integer | 是 | 评论的ID |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回空对象表示删除成功。

### 响应示例

```json
{}
```

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/comments/:id"
params = {"access_token": "YOUR_TOKEN"}

response = requests.delete(url, params=params)
print(response.status_code)
```
