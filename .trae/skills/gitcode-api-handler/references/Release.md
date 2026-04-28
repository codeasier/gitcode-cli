# Release 接口文档

从 GitCode API 文档中提取的 Release 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 8个

## 接口列表

### Release 基础操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 创建仓库Release | POST | `/repos/:owner/:repo/releases` | [详细文档](Release/create-release.md) |
| 2 | 更新仓库Release | PATCH | `/repos/:owner/:repo/releases/:tag` | [详细文档](Release/update-release.md) |
| 3 | 获取仓库的所有Releases | GET | `/repos/:owner/:repo/releases` | [详细文档](Release/get-releases.md) |
| 4 | 获取仓库的单个Releases | GET | `/repos/:owner/:repo/releases/:tag` | [详细文档](Release/get-release-by-tag.md) |
| 5 | 获取仓库的最后更新的Release | GET | `/repos/:owner/:repo/releases/latest` | [详细文档](Release/get-latest-release.md) |
| 6 | 根据Tag名称获取仓库的Release | GET | `/repos/:owner/:repo/releases/tags/:tag` | [详细文档](Release/get-release-by-tag-name.md) |

### Release 附件操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 7 | 获取Release附件上传地址 | GET | `/repos/:owner/:repo/releases/:tag/upload_url` | [详细文档](Release/get-release-upload-url.md) |
| 8 | 下载仓库release附件 | GET | `/repos/:owner/:repo/releases/:tag/attach_files/:file_name/download` | [详细文档](Release/download-release-attachment.md) |

## 接口概览

### 1. 创建仓库Release

> 详细文档: [create-release.md](Release/create-release.md)

创建一个新的仓库 Release 版本。

**请求示例**:
```bash
POST /repos/:owner/:repo/releases?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "tag_name": "v1.0.0",
  "name": "Version 1.0.0",
  "body": "这是第一个正式版本发布",
  "target_commitish": "master"
}
```

---

### 2. 更新仓库Release

> 详细文档: [update-release.md](Release/update-release.md)

更新指定仓库的 Release 版本信息。

**请求示例**:
```bash
PATCH /repos/:owner/:repo/releases/:tag?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "name": "Version 1.0.1",
  "body": "修复了一些已知问题"
}
```

---

### 3. 获取仓库的所有Releases

> 详细文档: [get-releases.md](Release/get-releases.md)

获取仓库的所有 Release 版本列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases?access_token=YOUR_TOKEN&page=1&per_page=20
```

---

### 4. 获取仓库的单个Releases

> 详细文档: [get-release-by-tag.md](Release/get-release-by-tag.md)

获取仓库指定 Tag 的 Release 详情。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases/:tag?access_token=YOUR_TOKEN&temp_download_url=true
```

---

### 5. 获取仓库的最后更新的Release

> 详细文档: [get-latest-release.md](Release/get-latest-release.md)

获取仓库最新发布的 Release 版本信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases/latest?access_token=YOUR_TOKEN
```

---

### 6. 根据Tag名称获取仓库的Release

> 详细文档: [get-release-by-tag-name.md](Release/get-release-by-tag-name.md)

根据 Tag 名称获取仓库的 Release 信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases/tags/:tag?access_token=YOUR_TOKEN
```

---

### 7. 获取Release附件上传地址

> 详细文档: [get-release-upload-url.md](Release/get-release-upload-url.md)

获取指定 Release 的附件上传地址。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases/:tag/upload_url?access_token=YOUR_TOKEN
```

---

### 8. 下载仓库release附件

> 详细文档: [download-release-attachment.md](Release/download-release-attachment.md)

下载指定 Release 的附件文件。

**请求示例**:
```bash
GET /repos/:owner/:repo/releases/:tag/attach_files/:file_name/download?access_token=YOUR_TOKEN
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 6个 |
| POST 请求 | 1个 |
| PATCH 请求 | 1个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
