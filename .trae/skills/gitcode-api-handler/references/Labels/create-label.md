# 创建仓库任务标签

为指定仓库创建一个新标签。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-labels

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
| name | string | 是 | 标签名称 |
| color | string | 是 | 标签颜色（十六进制，不带#） |
| description | string | 否 | 标签描述 |

## 响应

### 响应结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | 标签ID |
| name | string | 标签名称 |
| color | string | 标签颜色（十六进制） |
| description | string | 标签描述 |
| default | boolean | 是否为默认标签 |

### 响应示例

```json
{
  "id": 10,
  "name": "feature",
  "color": "0e8a16",
  "description": "New feature implementation",
  "default": false
}
```

## 请求示例

### cURL

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/labels?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=feature&color=0e8a16&description=New feature implementation"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/labels"
params = {
}
data = {
    "name": "feature",
    "color": "0e8a16",
    "description": "New feature implementation"
}

response = requests.post(url, params=params, data=data)
print(response.json())
```
