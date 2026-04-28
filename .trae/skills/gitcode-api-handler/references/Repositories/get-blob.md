# 获取文件Blob

获取指定文件的Blob内容。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/git/blobs/:sha`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-git-blobs-sha

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| sha | string | 是 | blob的SHA值 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应字段

文档未提供详细响应结构。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/git/blobs/:sha?access_token=YOUR_TOKEN"
```

## 相关接口

- [获取仓库目录Tree](get-git-trees.md)
- [获取仓库具体路径下的内容](get-contents.md)
