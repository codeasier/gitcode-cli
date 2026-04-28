# 上传图片

上传图片到指定仓库。

## 基本信息

- **方法**: POST
- **路径**: `/repos/:owner/:repo/img/upload`
- **文档URL**: https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-img-upload

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
| file | file | 是 | 图片文件,支持格式:jpg、jpeg、png、gif、bmp、webp等 |
| path | string | 否 | 存储路径,默认为根目录 |
| message | string | 否 | 提交信息 |
| branch | string | 否 | 分支名称,默认为仓库默认分支 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| url | string | 图片访问URL |
| path | string | 图片存储路径 |
| name | string | 图片文件名 |
| size | integer | 图片大小(字节) |
| sha | string | 文件SHA值 |
| html_url | string | 网页URL |
| download_url | string | 下载URL |

## 请求示例

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/:owner/:repo/img/upload?access_token=YOUR_TOKEN" \
  -F "file=@/path/to/image.png" \
  -F "path=images" \
  -F "message=Upload image" \
  -F "branch=main"
```

## 响应示例

```json
{
  "url": "https://api.gitcode.com/api/v5/repos/owner/repo/contents/images/image.png",
  "path": "images/image.png",
  "name": "image.png",
  "size": 12345,
  "sha": "abc123def456abc123def456abc123def456abc1",
  "html_url": "https://gitcode.com/owner/repo/blob/main/images/image.png",
  "download_url": "https://gitcode.com/owner/repo/raw/main/images/image.png"
}
```

## 相关接口

- [上传文件](upload-file.md)
- [新建文件](create-file.md)
- [获取仓库具体路径下的内容](get-contents.md)
