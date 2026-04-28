# 上传文件

上传文件到指定仓库。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/file/upload`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-file-upload

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体参数

使用 `multipart/form-data` 格式上传:

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| file | file | 是 | 要上传的文件 |
| path | string | 否 | 存储路径,默认为根目录 |
| message | string | 否 | 提交信息 |
| branch | string | 否 | 分支名称,默认为仓库默认分支 |
| author[name] | string | 否 | 作者姓名 |
| author[email] | string | 否 | 作者邮箱 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| content | object | 文件内容对象 |
| └─ type | string | 类型 |
| └─ encoding | string | 编码方式 |
| └─ size | integer | 文件大小 |
| └─ name | string | 文件名 |
| └─ path | string | 文件路径 |
| └─ sha | string | 文件SHA值 |
| └─ url | string | API URL |
| └─ html_url | string | 网页URL |
| └─ download_url | string | 下载URL |
| commit | object | 提交对象 |
| └─ sha | string | 提交SHA |
| └─ html_url | string | 提交网页URL |
| └─ message | string | 提交信息 |
| └─ author | object | 作者信息 |
| &nbsp;&nbsp;&nbsp;└─ name | string | 作者姓名 |
| &nbsp;&nbsp;&nbsp;└─ email | string | 作者邮箱 |
| &nbsp;&nbsp;&nbsp;└─ date | string | ISO 8601格式时间 |

## 请求示例

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/file/upload?access_token=YOUR_TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "path=documents" \
  -F "message=Upload document" \
  -F "branch=main" \
  -F "author[name]=John Doe" \
  -F "author[email]=john@example.com"
```

## 响应示例

```json
{
  "content": {
    "type": "file",
    "encoding": "base64",
    "size": 123456,
    "name": "document.pdf",
    "path": "documents/document.pdf",
    "sha": "abc123def456abc123def456abc123def456abc1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/documents/document.pdf",
    "html_url": "https://gitcode.com/owner/repo/blob/main/documents/document.pdf",
    "download_url": "https://gitcode.com/owner/repo/raw/main/documents/document.pdf"
  },
  "commit": {
    "sha": "def456abc123def456abc123def456abc123def4",
    "html_url": "https://gitcode.com/owner/repo/commit/def456abc123",
    "message": "Upload document",
    "author": {
      "name": "John Doe",
      "email": "john@example.com",
      "date": "2024-01-01T12:00:00Z"
    }
  }
}
```

## 相关接口

- [上传图片](upload-image.md)
- [新建文件](create-file.md)
- [更新文件](update-file.md)
