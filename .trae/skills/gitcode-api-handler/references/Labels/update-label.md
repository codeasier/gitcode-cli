# 更新一个仓库的任务标签

更新指定仓库的某个标签信息。

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/labels/:original_name`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-labels-original-name

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| original_name | string | 是 | 原标签名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 否 | 新标签名称 |
| color | string | 否 | 标签颜色（十六进制，不带#） |
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
  "id": 1,
  "name": "bug-fixed",
  "color": "d73a4a",
  "description": "Bug has been fixed",
  "default": false
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/labels/:original_name?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=bug-fixed&color=d73a4a&description=Bug has been fixed"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/labels/bug"
params = {
}
data = {
    "name": "bug-fixed",
    "color": "d73a4a",
    "description": "Bug has been fixed"
}

response = requests.patch(url, params=params, data=data)
print(response.json())
```
