# 获取文件列表

获取指定仓库的文件列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/file_list`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-file-list

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
| ref_name | string | 否 | 分支名称 |
| file_name | string | 否 | 文件名称 |

## 响应字段

返回文件列表数组,每个元素包含文件的基本信息。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/file_list?access_token=YOUR_TOKEN&ref_name=master"
```

## 响应示例

```json
[
  {
    "name": "README.md",
    "path": "README.md",
    "type": "file",
    "sha": "abc123def456abc123def456abc123def456abc1",
    "size": 1234
  },
  {
    "name": "src",
    "path": "src",
    "type": "dir",
    "sha": "dir123abc456def123abc456def123abc456"
  },
  {
    "name": "package.json",
    "path": "package.json",
    "type": "file",
    "sha": "pkg123abc456def123abc456def123abc456",
    "size": 567
  }
]
```

## 相关接口

- [获取仓库目录Tree](get-git-trees.md)
- [获取仓库具体路径下的内容](get-contents.md)
