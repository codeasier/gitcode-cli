# 删除一个仓库任务标签

删除指定仓库的某个标签。

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo/labels/:name`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-labels-name

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| name | string | 是 | 标签名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回空响应体，HTTP状态码 204 表示删除成功。

### 响应示例

```
HTTP/1.1 204 No Content
```

## 请求示例

### cURL

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo/labels/:name?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/labels/feature"
params = {
}

response = requests.delete(url, params=params)
print(response.status_code)
```
