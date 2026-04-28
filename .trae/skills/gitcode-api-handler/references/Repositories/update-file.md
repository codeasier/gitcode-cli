# 更新文件

更新指定仓库中的文件内容。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/contents/:path`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-contents-path

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| path | string | 是 | 文件路径(包含文件名) |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| content | string | 是 | 文件内容,必须为Base64编码的字符串 |
| sha | string | 是 | 文件的SHA值(必须提供,用于验证文件未被修改) |
| message | string | 是 | 提交信息 |
| branch | string | 否 | 分支名称,默认为仓库默认分支 |
| author[name] | string | 否 | 作者姓名 |
| author[email] | string | 否 | 作者邮箱 |
| committer[name] | string | 否 | 提交者姓名 |
| committer[email] | string | 否 | 提交者邮箱 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| content | object | 文件内容对象 |
| └─ type | string | 类型 |
| └─ encoding | string | 编码方式 |
| └─ size | integer | 文件大小 |
| └─ name | string | 文件名 |
| └─ path | string | 文件路径 |
| └─ content | string | Base64编码的内容 |
| └─ sha | string | 文件SHA值 |
| └─ url | string | API URL |
| └─ git_url | string | Git API URL |
| └─ html_url | string | 网页URL |
| └─ download_url | string | 下载URL |
| └─ _links | object | 链接对象 |
| commit | object | 提交对象 |
| └─ sha | string | 提交SHA |
| └─ html_url | string | 提交网页URL |
| └─ author | object | 作者信息 |
| &nbsp;&nbsp;&nbsp;└─ name | string | 作者姓名 |
| &nbsp;&nbsp;&nbsp;└─ email | string | 作者邮箱 |
| &nbsp;&nbsp;&nbsp;└─ date | string | ISO 8601格式时间 |
| └─ committer | object | 提交者信息 |
| &nbsp;&nbsp;&nbsp;└─ name | string | 提交者姓名 |
| &nbsp;&nbsp;&nbsp;└─ email | string | 提交者邮箱 |
| &nbsp;&nbsp;&nbsp;└─ date | string | ISO 8601格式时间 |
| └─ message | string | 提交信息 |
| └─ tree | object | 目录树信息 |
| &nbsp;&nbsp;&nbsp;└─ sha | string | 目录树SHA |
| &nbsp;&nbsp;&nbsp;└─ url | string | 目录树URL |
| └─ parents | array | 父提交数组 |
| &nbsp;&nbsp;&nbsp;└─ sha | string | 父提交SHA |
| &nbsp;&nbsp;&nbsp;└─ url | string | 父提交URL |
| &nbsp;&nbsp;&nbsp;└─ html_url | string | 父提交网页URL |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "IyBHaXRDb2RlIEFQSSBVcGRhdGVk",
    "sha": "abc123def456abc123def456abc123def456abc1",
    "message": "Update file content",
    "branch": "master"
  }'
```

## 响应示例

```json
{
  "content": {
    "type": "file",
    "encoding": "base64",
    "size": 2345,
    "name": "README.md",
    "path": "docs/README.md",
    "content": "IyBHaXRDb2RlIEFQSSBVcGRhdGVk",
    "sha": "new123sha456new123sha456new123sha456new",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/docs/README.md",
    "git_url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/new123",
    "html_url": "https://gitcode.com/owner/repo/blob/master/docs/README.md",
    "download_url": "https://gitcode.com/owner/repo/raw/master/docs/README.md",
    "_links": {
      "git": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/new123",
      "self": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/docs/README.md",
      "html": "https://gitcode.com/owner/repo/blob/master/docs/README.md"
    }
  },
  "commit": {
    "sha": "commit456abc123def456abc123def456abc1",
    "html_url": "https://gitcode.com/owner/repo/commit/commit456",
    "author": {
      "name": "John Doe",
      "email": "john@example.com",
      "date": "2024-01-01T12:00:00Z"
    },
    "committer": {
      "name": "John Doe",
      "email": "john@example.com",
      "date": "2024-01-01T12:00:00Z"
    },
    "message": "Update file content",
    "tree": {
      "sha": "tree456abc123def456abc123def456abc12",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/trees/tree456"
    },
    "parents": [
      {
        "sha": "parent456abc123def456abc123def456abc",
        "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/parent456",
        "html_url": "https://gitcode.com/owner/repo/commit/parent456"
      }
    ]
  }
}
```

## 相关接口

- [获取仓库具体路径下的内容](get-contents.md)
- [新建文件](create-file.md)
- [删除文件](delete-file.md)
