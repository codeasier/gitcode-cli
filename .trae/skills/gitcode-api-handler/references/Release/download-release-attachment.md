# 下载仓库release附件

下载指定 Release 的附件文件。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/releases/:tag/attach_files/:file_name/download`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-releases-attach-files-file-name-download

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址（企业、组织或个人的地址path） |
| repo | string | 是 | 仓库路径(path) |
| tag | string | 是 | Tag 名称 |
| file_name | string | 是 | 文件名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应说明

成功调用此接口将返回文件内容，响应头中包含：
- Content-Type: 文件类型
- Content-Disposition: 包含文件名的附件信息
- Content-Length: 文件大小

### 响应示例

返回二进制文件流，可直接下载。

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/releases/:tag/attach_files/:file_name/download?access_token=YOUR_TOKEN" \
  -H "Accept: */*" \
  -o downloaded_file.zip
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/owner/repo/releases/tag_name/attach_files/app-v1.0.0.zip/download"
params = {"access_token": "YOUR_TOKEN"}

response = requests.get(url, params=params)
with open("app-v1.0.0.zip", "wb") as f:
    f.write(response.content)
print("文件下载完成")
```
