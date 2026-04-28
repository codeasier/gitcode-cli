# 获取仓库目录Tree

获取指定仓库的目录树结构。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/git/trees/:sha`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-git-trees-sha

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| sha | string | 是 | 可以是分支名称(如master)、提交SHA值或标签名称 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| recursive | integer | 否 | 是否递归获取目录树,1表示递归,0表示不递归 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| sha | string | 目录树的SHA值 |
| url | string | API URL |
| tree | array | 文件和目录数组 |
| └─ mode | string | 文件模式(如100644表示普通文件,040000表示目录) |
| └─ type | string | 类型:"blob"表示文件,"tree"表示目录 |
| └─ sha | string | 文件或目录的SHA值 |
| └─ path | string | 相对路径 |
| └─ size | integer | 文件大小(仅文件有此字段) |
| truncated | boolean | 是否被截断 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/git/trees/:sha?access_token=YOUR_TOKEN"
```

## 响应示例

```json
{
  "sha": "9fb037999f264ba9a7fc6274d15fa3ae2ab98312",
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/git/trees/9fb037999f264ba9a7fc6274d15fa3ae2ab98312",
  "tree": [
    {
      "mode": "100644",
      "type": "blob",
      "sha": "ef7e6b2e8c8e8c8e8c8e8c8e8c8e8c8e8c8e8c8e",
      "path": "README.md",
      "size": 1234
    },
    {
      "mode": "040000",
      "type": "tree",
      "sha": "abc123def456abc123def456abc123def456abc1",
      "path": "src"
    }
  ],
  "truncated": false
}
```

## 相关接口

- [获取仓库具体路径下的内容](get-contents.md)
- [获取文件Blob](get-blob.md)
