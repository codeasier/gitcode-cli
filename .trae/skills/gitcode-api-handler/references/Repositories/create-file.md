# 新建文件

在指定仓库中创建新文件。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/contents/:path`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-contents-path

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
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "IyBHaXRDb2RlIEFQSQ==",
    "message": "Add new file",
    "branch": "master"
  }'
```

## 响应示例

```json
{
  "content": {
    "type": "file",
    "encoding": "base64",
    "size": 1234,
    "name": "newfile.md",
    "path": "docs/newfile.md",
    "content": "IyBHaXRDb2RlIEFQSQ==",
    "sha": "abc123def456abc123def456abc123def456abc1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/docs/newfile.md",
    "git_url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/abc123",
    "html_url": "https://gitcode.com/owner/repo/blob/master/docs/newfile.md",
    "download_url": "https://gitcode.com/owner/repo/raw/master/docs/newfile.md",
    "_links": {
      "git": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/abc123",
      "self": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/docs/newfile.md",
      "html": "https://gitcode.com/owner/repo/blob/master/docs/newfile.md"
    }
  },
  "commit": {
    "sha": "def456abc123def456abc123def456abc123def4",
    "html_url": "https://gitcode.com/owner/repo/commit/def456abc123",
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
    "message": "Add new file",
    "tree": {
      "sha": "tree123def456abc123def456abc123def456",
      "url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/trees/tree123"
    },
    "parents": [
      {
        "sha": "parent123def456abc123def456abc123def",
        "url": "https://api.gitcode.com/api/v5/repos/owner/repo/commits/parent123",
        "html_url": "https://gitcode.com/owner/repo/commit/parent123"
      }
    ]
  }
}
```

## 相关接口

- [获取仓库具体路径下的内容](get-contents.md)
- [更新文件](update-file.md)
- [删除文件](delete-file.md)
