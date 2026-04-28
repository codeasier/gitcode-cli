# Tag 接口文档

从 GitCode API 文档中提取的 Tag 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 8个

## 接口列表

### 标签基础操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 列出项目所有的tags | GET | `/repos/:owner/:repo/tags` | [详细文档](Tag/get-tags.md) |
| 2 | 创建一个仓库的Tag | POST | `/repos/:owner/:repo/tags` | [详细文档](Tag/create-tag.md) |
| 3 | 删除仓库的一个Tag | DELETE | `/repos/:owner/:repo/tags/:tag_name` | [详细文档](Tag/delete-tag.md) |

### 保护标签规则

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 4 | 列出项目保护tags | GET | `/repos/:owner/:repo/protected_tags` | [详细文档](Tag/get-protected-tags.md) |
| 5 | 创建项目保护tag | POST | `/repos/:owner/:repo/protected_tags` | [详细文档](Tag/create-protected-tag.md) |
| 6 | 修改项目保护tag | PUT | `/repos/:owner/:repo/protected_tags` | [详细文档](Tag/update-protected-tag.md) |
| 7 | 删除项目保护tag | DELETE | `/repos/:owner/:repo/protected_tags/:tag_name` | [详细文档](Tag/delete-protected-tag.md) |
| 8 | 获取项目保护tag详情 | GET | `/repos/:owner/:repo/protected_tags/:tag_name` | [详细文档](Tag/get-protected-tag.md) |

## 接口概览

### 1. 列出项目所有的tags

> 详细文档: [get-tags.md](Tag/get-tags.md)

获取指定仓库的所有标签列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/tags?access_token=YOUR_TOKEN
```

---

### 2. 创建一个仓库的Tag

> 详细文档: [create-tag.md](Tag/create-tag.md)

在指定仓库中创建一个新标签。

**请求示例**:
```bash
POST /repos/:owner/:repo/tags?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "refs": "master",
  "tag_name": "v1.0.0",
  "tag_message": "Release version 1.0.0"
}
```

---

### 3. 删除仓库的一个Tag

> 详细文档: [delete-tag.md](Tag/delete-tag.md)

删除指定仓库中的一个标签。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/tags/:tag_name?access_token=YOUR_TOKEN
```

---

### 4. 列出项目保护tags

> 详细文档: [get-protected-tags.md](Tag/get-protected-tags.md)

获取指定仓库的所有保护标签列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/protected_tags?access_token=YOUR_TOKEN
```

---

### 5. 创建项目保护tag

> 详细文档: [create-protected-tag.md](Tag/create-protected-tag.md)

为指定仓库创建一个保护标签规则。

**请求示例**:
```bash
POST /repos/:owner/:repo/protected_tags?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "name": "v*",
  "create_access_level": 40
}
```

---

### 6. 修改项目保护tag

> 详细文档: [update-protected-tag.md](Tag/update-protected-tag.md)

更新指定仓库的一个保护标签规则。

**请求示例**:
```bash
PUT /repos/:owner/:repo/protected_tags?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "name": "v*",
  "create_access_level": 30
}
```

---

### 7. 删除项目保护tag

> 详细文档: [delete-protected-tag.md](Tag/delete-protected-tag.md)

删除指定仓库中的一个保护标签规则。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/protected_tags/:tag_name?access_token=YOUR_TOKEN
```

---

### 8. 获取项目保护tag详情

> 详细文档: [get-protected-tag.md](Tag/get-protected-tag.md)

获取指定仓库中某个保护标签规则的详细信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/protected_tags/:tag_name?access_token=YOUR_TOKEN
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 3个 |
| POST 请求 | 2个 |
| PUT 请求 | 1个 |
| DELETE 请求 | 2个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
