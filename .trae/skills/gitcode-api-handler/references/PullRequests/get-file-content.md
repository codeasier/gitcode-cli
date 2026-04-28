# 获取文件内容

获取文件内容

## 基本信息

- **方法**: GET
- **路径**: `/:owner/:repo/raw/:head_sha/:name`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-owner-repo-raw-head-sha-name

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| head_sha | string | 是 | 提交SHA |
| name | string | 是 | 文件路径 |

## 响应

返回文件的原始内容。

### 响应示例

```
文件原始内容...
```

## 请求示例

### cURL

```bash
curl -X GET "https://raw.gitcode.com/:owner/:repo/raw/:head_sha/:name" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = f"https://raw.gitcode.com/{owner}/{repo}/raw/{head_sha}/{name}"

response = requests.get(url)
print(response.text)
```
