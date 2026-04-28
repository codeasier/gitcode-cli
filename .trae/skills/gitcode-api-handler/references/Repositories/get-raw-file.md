# 获取 raw 文件

获取文件的原始内容。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/raw/:path`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-raw-path

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| path | string | 是 | 文件路径 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| ref | string | 否 | 分支、标签或commit SHA |

## 响应字段

返回文件的原始内容。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/raw/:path?access_token=YOUR_TOKEN"
```

## 相关接口

- [获取仓库具体路径下的内容](get-contents.md)
- [获取文件Blob](get-blob.md)
