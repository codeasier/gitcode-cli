# Commit 接口文档

从 GitCode API 文档中提取的 Commit 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 12个

## 接口列表

### 提交查询

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 获取仓库所有提交 | GET | `/repos/:owner/:repo/commits` | [详细文档](Commit/get-repo-commits.md) |
| 2 | 仓库的某个提交 | GET | `/repos/:owner/:repo/commits/:sha` | [详细文档](Commit/get-commit.md) |
| 3 | Commits对比 | GET | `/repos/:owner/:repo/compare/:base...:head` | [详细文档](Commit/compare-commits.md) |

### 评论管理

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 4 | 创建commit评论 | POST | `/repos/:owner/:repo/commits/:sha/comments` | [详细文档](Commit/create-commit-comment.md) |
| 5 | 删除commit评论 | DELETE | `/repos/:owner/:repo/comments/:id` | [详细文档](Commit/delete-commit-comment.md) |
| 6 | 获取仓库的某条Commit评论 | GET | `/repos/:owner/:repo/comments/:id` | [详细文档](Commit/get-commit-comment.md) |
| 7 | 更新Commit评论 | PATCH | `/repos/:owner/:repo/comments/:id` | [详细文档](Commit/update-commit-comment.md) |
| 8 | 获取仓库的Commit评论 | GET | `/repos/:owner/:repo/comments` | [详细文档](Commit/get-repo-comments.md) |
| 9 | 获取单个commit评论 | GET | `/repos/:owner/:repo/commits/:ref/comments` | [详细文档](Commit/get-commit-comments.md) |

### 统计与导出

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 10 | 获取代码量贡献 | GET | `/:owner/:repo/repository/commit_statistics` | [详细文档](Commit/get-commit-statistics.md) |
| 11 | 获取commit的diff | GET | `/repos/:owner/:repo/commit/:sha/diff` | [详细文档](Commit/get-commit-diff.md) |
| 12 | 获取commit的patch | GET | `/repos/:owner/:repo/commit/:sha/patch` | [详细文档](Commit/get-commit-patch.md) |

## 接口概览

### 1. 获取仓库所有提交

> 详细文档: [get-repo-commits.md](Commit/get-repo-commits.md)

获取指定仓库的所有提交记录列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/commits?access_token=YOUR_TOKEN
```

---

### 2. 仓库的某个提交

> 详细文档: [get-commit.md](Commit/get-commit.md)

获取指定仓库中某个提交的详细信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/commits/:sha?access_token=YOUR_TOKEN
```

---

### 3. Commits对比

> 详细文档: [compare-commits.md](Commit/compare-commits.md)

比较两个提交之间的差异。

**请求示例**:
```bash
GET /repos/:owner/:repo/compare/:base...:head?access_token=YOUR_TOKEN
```

---

### 4. 创建commit评论

> 详细文档: [create-commit-comment.md](Commit/create-commit-comment.md)

为指定的提交创建评论。

**请求示例**:
```bash
POST /repos/:owner/:repo/commits/:sha/comments?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "body": "这是一条评论内容"
}
```

---

### 5. 删除commit评论

> 详细文档: [delete-commit-comment.md](Commit/delete-commit-comment.md)

删除指定的提交评论。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/comments/:id?access_token=YOUR_TOKEN
```

---

### 6. 获取仓库的某条Commit评论

> 详细文档: [get-commit-comment.md](Commit/get-commit-comment.md)

获取指定仓库中某条提交评论的详细信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/comments/:id?access_token=YOUR_TOKEN
```

---

### 7. 更新Commit评论

> 详细文档: [update-commit-comment.md](Commit/update-commit-comment.md)

更新指定的提交评论内容。

**请求示例**:
```bash
PATCH /repos/:owner/:repo/comments/:id?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "body": "更新后的评论内容"
}
```

---

### 8. 获取仓库的Commit评论

> 详细文档: [get-repo-comments.md](Commit/get-repo-comments.md)

获取指定仓库的所有提交评论列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/comments?access_token=YOUR_TOKEN&page=1&per_page=20
```

---

### 9. 获取单个commit评论

> 详细文档: [get-commit-comments.md](Commit/get-commit-comments.md)

获取指定提交的所有评论列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/commits/:ref/comments?access_token=YOUR_TOKEN
```

---

### 10. 获取代码量贡献

> 详细文档: [get-commit-statistics.md](Commit/get-commit-statistics.md)

获取指定仓库的代码量贡献统计。

**请求示例**:
```bash
GET /:owner/:repo/repository/commit_statistics?access_token=YOUR_TOKEN&branch_name=main
```

---

### 11. 获取commit的diff

> 详细文档: [get-commit-diff.md](Commit/get-commit-diff.md)

获取指定提交的diff信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/commit/:sha/diff?access_token=YOUR_TOKEN
```

---

### 12. 获取commit的patch

> 详细文档: [get-commit-patch.md](Commit/get-commit-patch.md)

获取指定提交的patch信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/commit/:sha/patch?access_token=YOUR_TOKEN
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 9个 |
| POST 请求 | 1个 |
| PATCH 请求 | 1个 |
| DELETE 请求 | 1个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
