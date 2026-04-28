# 判断Pull Request是否合并

判断Pull Request是否合并

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pulls/:number/merge`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number-merge

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
| merged | boolean | 是否已合并 |
| message | string | 状态消息 |

### 响应示例

```json
{
  "merged": true,
  "message": "Pull Request has been merged"
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/merge?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/merge"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
