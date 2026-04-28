# 获取仓库具体路径下的内容

获取指定仓库中某个文件或目录的内容。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/contents/:path`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contents-path

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| path | string | 是 | 文件或目录的路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| ref | string | 否 | 分支名称、标签名称或commit SHA,默认为仓库默认分支 |

## 响应字段

### 文件响应

| 字段名 | 类型 | 描述 |
|--------|------|------|
| type | string | 类型,值为"file" |
| encoding | string | 编码方式,通常为"base64" |
| size | integer | 文件大小(字节) |
| name | string | 文件名 |
| path | string | 文件路径 |
| content | string | Base64编码的文件内容 |
| sha | string | 文件SHA值 |
| url | string | API URL |
| git_url | string | Git API URL |
| html_url | string | 网页URL |
| download_url | string | 下载URL |
| _links | object | 链接对象 |
| └─ git | string | Git链接 |
| └─ self | string | 自身链接 |
| └─ html | string | HTML链接 |

### 目录响应

返回数组,每个元素包含:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| type | string | 类型:"file"、"dir"、"symlink"、"submodule" |
| size | integer | 文件大小(仅文件有此字段) |
| name | string | 文件或目录名 |
| path | string | 路径 |
| sha | string | SHA值 |
| url | string | API URL |
| git_url | string | Git API URL |
| html_url | string | 网页URL |
| download_url | string | 下载URL |
| _links | object | 链接对象 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN"
```

## 响应示例

### 文件响应示例

```json
{
  "type": "file",
  "encoding": "base64",
  "size": 1234,
  "name": "README.md",
  "path": "README.md",
  "content": "IyBHaXRDb2RlIEFQSQ==",
  "sha": "abc123def456abc123def456abc123def456abc1",
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/README.md",
  "git_url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/abc123",
  "html_url": "https://gitcode.com/owner/repo/blob/master/README.md",
  "download_url": "https://gitcode.com/owner/repo/raw/master/README.md",
  "_links": {
    "git": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/abc123",
    "self": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/README.md",
    "html": "https://gitcode.com/owner/repo/blob/master/README.md"
  }
}
```

### 目录响应示例

```json
[
  {
    "type": "file",
    "size": 1234,
    "name": "README.md",
    "path": "README.md",
    "sha": "abc123def456abc123def456abc123def456abc1",
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/README.md",
    "git_url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/blobs/abc123",
    "html_url": "https://gitcode.com/owner/repo/blob/master/README.md",
    "download_url": "https://gitcode.com/owner/repo/raw/master/README.md",
    "_links": {}
  }
]
```

## 相关接口

- [新建文件](create-file.md)
- [更新文件](update-file.md)
- [删除文件](delete-file.md)
