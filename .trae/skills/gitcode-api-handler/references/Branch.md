# Branch 接口文档

从 GitCode API 文档中提取的 Branch 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 8个

## 接口列表

### 分支基础操作

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 获取项目所有分支 | GET | `/repos/:owner/:repo/branches` | [详细文档](Branch/get-branches.md) |
| 2 | 创建分支 | POST | `/repos/:owner/:repo/branches` | [详细文档](Branch/create-branch.md) |
| 3 | 删除分支 | DELETE | `/repos/:owner/:repo/branches/:name` | [详细文档](Branch/delete-branch.md) |
| 4 | 获取单个分支 | GET | `/repos/:owner/:repo/branches/:branch` | [详细文档](Branch/get-branch.md) |

### 保护分支规则

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 5 | 新建保护分支规则 | PUT | `/repos/:owner/:repo/branches/setting/new` | [详细文档](Branch/create-protect-rule.md) |
| 6 | 删除保护分支规则 | DELETE | `/repos/:owner/:repo/branches/:wildcard/setting` | [详细文档](Branch/delete-protect-rule.md) |
| 7 | 获取保护分支规则列表 | GET | `/repos/:owner/:repo/protect_branches` | [详细文档](Branch/get-protect-rules.md) |
| 8 | 更新保护分支规则 | PUT | `/repos/:owner/:repo/branches/:wildcard/setting` | [详细文档](Branch/update-protect-rule.md) |

## 接口概览

### 1. 获取项目所有分支

> 详细文档: [get-branches.md](Branch/get-branches.md)

获取指定仓库的所有分支列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/branches?access_token=YOUR_TOKEN
```

---

### 2. 创建分支

> 详细文档: [create-branch.md](Branch/create-branch.md)

在指定仓库中创建一个新分支。

**请求示例**:
```bash
POST /repos/:owner/:repo/branches?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "refs": "master",
  "branch_name": "feature-new"
}
```

---

### 3. 删除分支

> 详细文档: [delete-branch.md](Branch/delete-branch.md)

删除指定仓库中的一个分支。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/branches/:name?access_token=YOUR_TOKEN
```

---

### 4. 获取单个分支

> 详细文档: [get-branch.md](Branch/get-branch.md)

获取指定仓库中某个分支的详细信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/branches/:branch?access_token=YOUR_TOKEN
```

---

### 5. 新建保护分支规则

> 详细文档: [create-protect-rule.md](Branch/create-protect-rule.md)

为指定仓库创建一个新的保护分支规则。

**请求示例**:
```bash
PUT /repos/:owner/:repo/branches/setting/new?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "wildcard": "release-*",
  "pusher": "user1,user2",
  "merger": "user1"
}
```

---

### 6. 删除保护分支规则

> 详细文档: [delete-protect-rule.md](Branch/delete-protect-rule.md)

删除指定仓库中的一个保护分支规则。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/branches/:wildcard/setting?access_token=YOUR_TOKEN
```

---

### 7. 获取保护分支规则列表

> 详细文档: [get-protect-rules.md](Branch/get-protect-rules.md)

获取指定仓库的所有保护分支规则。

**请求示例**:
```bash
GET /repos/:owner/:repo/protect_branches?access_token=YOUR_TOKEN
```

---

### 8. 更新保护分支规则

> 详细文档: [update-protect-rule.md](Branch/update-protect-rule.md)

更新指定仓库中的一个保护分支规则。

**请求示例**:
```bash
PUT /repos/:owner/:repo/branches/:wildcard/setting?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "pusher": "user1,user2,user3",
  "merger": "user1,user2"
}
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 3个 |
| POST 请求 | 1个 |
| PUT 请求 | 2个 |
| DELETE 请求 | 2个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
