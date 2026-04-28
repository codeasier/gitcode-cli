# Labels 接口文档

从 GitCode API 文档中提取的 Labels 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 9个

## 接口列表

### 仓库标签管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 获取仓库所有任务标签 | GET | `/repos/:owner/:repo/labels` | [详细文档](Labels/get-repo-labels.md) |
| 2 | 创建仓库任务标签 | POST | `/repos/:owner/:repo/labels` | [详细文档](Labels/create-label.md) |
| 3 | 更新一个仓库的任务标签 | PATCH | `/repos/:owner/:repo/labels/:original_name` | [详细文档](Labels/update-label.md) |
| 4 | 删除一个仓库任务标签 | DELETE | `/repos/:owner/:repo/labels/:name` | [详细文档](Labels/delete-label.md) |
| 5 | 替换所有仓库标签 | PUT | `/repos/:owner/:repo/project_labels` | [详细文档](Labels/replace-repo-labels.md) |

### Issue 标签管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 6 | 替换Issue所有标签 | PUT | `/repos/:owner/:repo/issues/:number/labels` | [详细文档](Labels/replace-issue-labels.md) |
| 7 | 删除Issue所有标签 | DELETE | `/repos/:owner/:repo/issues/:number/labels` | [详细文档](Labels/delete-issue-labels.md) |

### 企业标签管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 8 | 获取企业所有的标签 | GET | `/enterprises/:enterprise/labels` (v5) | [详细文档](Labels/get-enterprise-labels.md) |
| 9 | 获取标签列表 | GET | `/enterprises/:enterprise/labels` (v8) | [详细文档](Labels/get-enterprise-labels-v8.md) |

## 接口概览

### 1. 获取仓库所有任务标签

> 详细文档: [get-repo-labels.md](Labels/get-repo-labels.md)

获取指定仓库的所有标签列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/labels?access_token=YOUR_TOKEN&page=1&per_page=20
```

---

### 2. 创建仓库任务标签

> 详细文档: [create-label.md](Labels/create-label.md)

为指定仓库创建一个新标签。

**请求示例**:
```bash
POST /repos/:owner/:repo/labels?access_token=YOUR_TOKEN
Content-Type: application/x-www-form-urlencoded

name=feature&color=0e8a16&description=New feature implementation
```

---

### 3. 更新一个仓库的任务标签

> 详细文档: [update-label.md](Labels/update-label.md)

更新指定仓库的某个标签信息。

**请求示例**:
```bash
PATCH /repos/:owner/:repo/labels/:original_name?access_token=YOUR_TOKEN
Content-Type: application/x-www-form-urlencoded

name=bug-fixed&color=d73a4a&description=Bug has been fixed
```

---

### 4. 删除一个仓库任务标签

> 详细文档: [delete-label.md](Labels/delete-label.md)

删除指定仓库的某个标签。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/labels/:name?access_token=YOUR_TOKEN
```

---

### 5. 替换所有仓库标签

> 详细文档: [replace-repo-labels.md](Labels/replace-repo-labels.md)

替换指定仓库的所有标签。

**请求示例**:
```bash
PUT /repos/:owner/:repo/project_labels?access_token=YOUR_TOKEN
Content-Type: application/json

["bug", "enhancement"]
```

---

### 6. 替换Issue所有标签

> 详细文档: [replace-issue-labels.md](Labels/replace-issue-labels.md)

替换指定Issue的所有标签。

**请求示例**:
```bash
PUT /repos/:owner/:repo/issues/:number/labels?access_token=YOUR_TOKEN
Content-Type: application/json

["bug", "priority"]
```

---

### 7. 删除Issue所有标签

> 详细文档: [delete-issue-labels.md](Labels/delete-issue-labels.md)

删除指定Issue的所有标签。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/issues/:number/labels?access_token=YOUR_TOKEN
```

---

### 8. 获取企业所有的标签

> 详细文档: [get-enterprise-labels.md](Labels/get-enterprise-labels.md)

获取指定企业的所有标签列表。

**请求示例**:
```bash
GET /enterprises/:enterprise/labels?access_token=YOUR_TOKEN&page=1&per_page=20
```

---

### 9. 获取标签列表

> 详细文档: [get-enterprise-labels-v8.md](Labels/get-enterprise-labels-v8.md)

获取指定企业的标签列表（API v8版本）。

**请求示例**:
```bash
GET /enterprises/:enterprise/labels?access_token=YOUR_TOKEN&page=1&per_page=20
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 3个 |
| POST 请求 | 1个 |
| PUT 请求 | 2个 |
| PATCH 请求 | 1个 |
| DELETE 请求 | 2个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
