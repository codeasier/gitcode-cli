# 获取Release附件上传地址

获取指定 Release 的附件上传地址。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/releases/:tag/upload_url`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-releases-tag-upload-url

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| tag | string | 是 | Tag 名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构 (object)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| upload_url | string | 附件上传地址 |
| release_id | integer | Release ID |
| tag_name | string | Tag 名称 |

### 响应示例

```json
{
  "upload_url": "https://gitcode.com/api/v5/repos/owner/repo/releases/12345/assets",
  "release_id": 12345,
  "tag_name": "v1.0.0"
}
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/releases/:tag/upload_url?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/releases/tag_name/upload_url"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
print(response.json())
```
