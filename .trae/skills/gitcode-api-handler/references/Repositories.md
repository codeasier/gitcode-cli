# Repositories 接口文档

从 GitCode API 文档中提取的 Repositories 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 36个
- **认证方式**: 
  - 查询参数: `?access_token={your-token}`
  - 请求头: `Authorization: Bearer {your-token}`
  - 请求头: `PRIVATE-TOKEN: {your-token}`

## 接口列表

### 文件操作相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 获取仓库目录Tree | GET | `/repos/:owner/:repo/git/trees/:sha` | [详细文档](Repositories/get-git-trees.md) |
| 2 | 获取仓库具体路径下的内容 | GET | `/repos/:owner/:repo/contents/:path` | [详细文档](Repositories/get-contents.md) |
| 3 | 新建文件 | POST | `/repos/:owner/:repo/contents/:path` | [详细文档](Repositories/create-file.md) |
| 4 | 更新文件 | PUT | `/repos/:owner/:repo/contents/:path` | [详细文档](Repositories/update-file.md) |
| 5 | 删除文件 | DELETE | `/repos/:owner/:repo/contents/:path` | [详细文档](Repositories/delete-file.md) |
| 6 | 获取文件列表 | GET | `/repos/:owner/:repo/file_list` | [详细文档](Repositories/get-file-list.md) |
| 7 | 获取文件Blob | GET | `/repos/:owner/:repo/git/blobs/:sha` | [详细文档](Repositories/get-blob.md) |
| 8 | 获取 raw 文件 | GET | `/repos/:owner/:repo/raw/:path` | [详细文档](Repositories/get-raw-file.md) |

### 仓库信息相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 9 | 获取仓库的语言 | GET | `/repos/:owner/:repo/languages` | [详细文档](Repositories/get-languages.md) |
| 10 | 获取仓库贡献者 | GET | `/repos/:owner/:repo/contributors` | [详细文档](Repositories/get-contributors.md) |
| 11 | 获取仓库贡献者统计信息 | GET | `/repos/:owner/:repo/contributors/statistic` | [详细文档](Repositories/get-contributors-statistic.md) |
| 12 | 下载次数统计 | GET | `/repos/:owner/:repo/download_statistics` | [详细文档](Repositories/get-download-statistics.md) |
| 13 | 获取仓库动态 | GET | `/repos/:owner/:repo/events` | [详细文档](Repositories/get-repo-events.md) |

### 仓库设置相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 14 | 设置项目模块 | PUT | `/repos/:owner/:repo/module/setting` | [详细文档](Repositories/update-module-setting.md) |
| 15 | 更新仓库设置 | PATCH | `/repos/:owner/:repo` | [详细文档](Repositories/update-repo.md) |
| 16 | 删除一个仓库 | DELETE | `/repos/:owner/:repo` | [详细文档](Repositories/delete-repo.md) |
| 17 | 更新仓库设置(高级) | PUT | `/repos/:owner/:repo/repo_settings` | [详细文档](Repositories/update-repo-settings.md) |
| 18 | 获取仓库设置 | GET | `/repos/:owner/:repo/repo_settings` | [详细文档](Repositories/get-repo-settings.md) |
| 19 | 获取 Pull Request设置 | GET | `/repos/:owner/:repo/pull_request_settings` | [详细文档](Repositories/get-pull-request-settings.md) |
| 20 | 更新 Pull Request设置 | PUT | `/repos/:owner/:repo/pull_request_settings` | [详细文档](Repositories/update-pull-request-settings.md) |

### 权限与审查相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 21 | 修改项目代码审查设置 | PUT | `/repos/:owner/:repo/reviewer` | [详细文档](Repositories/update-reviewer.md) |
| 22 | 获取项目的权限模式 | GET | `/repos/:owner/:repo/transition` | [详细文档](Repositories/get-transition.md) |
| 23 | 更新仓库的权限模式 | PUT | `/repos/:owner/:repo/transition` | [详细文档](Repositories/update-transition.md) |
| 24 | 设置项目推送规则 | PUT | `/repos/:owner/:repo/push_config` | [详细文档](Repositories/update-push-config.md) |
| 25 | 获取项目推送规则 | GET | `/repos/:owner/:repo/push_config` | [详细文档](Repositories/get-push-config.md) |
| 26 | 更新项目成员角色 | PUT | `/repos/:owner/:repo/members/:username` | [详细文档](Repositories/update-member-role.md) |
| 27 | 获取项目自定义角色 | GET | `/repos/:owner/:repo/customized_roles` | [详细文档](Repositories/get-customized-roles.md) |

### Fork 与转移相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 28 | Fork一个仓库 | POST | `/repos/:owner/:repo/forks` | [详细文档](Repositories/fork-repo.md) |
| 29 | 查看仓库的Forks | GET | `/repos/:owner/:repo/forks` | [详细文档](Repositories/get-forks.md) |
| 30 | 仓库转移 | POST | `/repos/:owner/:repo/transfer` | [详细文档](Repositories/transfer-repo.md) |
| 31 | 转移仓(组织) | POST | `/org/:org/projects/:repo/transfer` | [详细文档](Repositories/org-transfer-repo.md) |
| 32 | 仓库归档 | PUT | `/org/:org/repo/:repo/status` | [详细文档](Repositories/archive-repo.md) |

### 上传相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 33 | 上传图片 | POST | `/repos/:owner/:repo/img/upload` | [详细文档](Repositories/upload-image.md) |
| 34 | 上传文件 | POST | `/repos/:owner/:repo/file/upload` | [详细文档](Repositories/upload-file.md) |

### Star 与 Watch 相关

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 35 | 列出 watch 了仓库的用户 | GET | `/repos/:owner/:repo/subscribers` | [详细文档](Repositories/get-subscribers.md) |
| 36 | 列出 star 了仓库的用户 | GET | `/repos/:owner/:repo/stargazers` | [详细文档](Repositories/get-stargazers.md) |

## 接口概览

### 1. 获取仓库目录Tree

> 详细文档: [get-git-trees.md](Repositories/get-git-trees.md)

获取指定仓库的目录树结构。

**请求示例**:
```bash
GET /repos/:owner/:repo/git/trees/:sha?access_token=YOUR_TOKEN
```

---

### 2. 获取仓库具体路径下的内容

> 详细文档: [get-contents.md](Repositories/get-contents.md)

获取指定仓库中某个文件或目录的内容。

**请求示例**:
```bash
GET /repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN
```

---

### 3. 新建文件

> 详细文档: [create-file.md](Repositories/create-file.md)

在指定仓库中创建一个新文件。

**请求示例**:
```bash
POST /repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "content": "base64-encoded-content",
  "message": "Create new file",
  "branch": "master"
}
```

---

### 4. 更新文件

> 详细文档: [update-file.md](Repositories/update-file.md)

更新指定仓库中的文件内容。

**请求示例**:
```bash
PUT /repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "content": "base64-encoded-content",
  "sha": "file-sha",
  "message": "Update file",
  "branch": "master"
}
```

---

### 5. 删除文件

> 详细文档: [delete-file.md](Repositories/delete-file.md)

删除指定仓库中的文件。

**请求示例**:
```bash
DELETE /repos/:owner/:repo/contents/:path?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "sha": "file-sha",
  "message": "Delete file",
  "branch": "master"
}
```

---

### 6. 获取文件列表

> 详细文档: [get-file-list.md](Repositories/get-file-list.md)

获取指定仓库的文件列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/file_list?access_token=YOUR_TOKEN
```

---

### 7. 获取文件Blob

> 详细文档: [get-blob.md](Repositories/get-blob.md)

获取指定文件的Blob内容。

**请求示例**:
```bash
GET /repos/:owner/:repo/git/blobs/:sha?access_token=YOUR_TOKEN
```

---

### 8. 获取 raw 文件

> 详细文档: [get-raw-file.md](Repositories/get-raw-file.md)

获取文件的原始内容。

**请求示例**:
```bash
GET /repos/:owner/:repo/raw/:path?access_token=YOUR_TOKEN
```

---

### 9. 获取仓库的语言

> 详细文档: [get-languages.md](Repositories/get-languages.md)

获取仓库使用的编程语言统计。

**请求示例**:
```bash
GET /repos/:owner/:repo/languages?access_token=YOUR_TOKEN
```

---

### 10. 获取仓库贡献者

> 详细文档: [get-contributors.md](Repositories/get-contributors.md)

获取仓库的贡献者列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/contributors?access_token=YOUR_TOKEN
```

---

### 11. 获取仓库贡献者统计信息

> 详细文档: [get-contributors-statistic.md](Repositories/get-contributors-statistic.md)

获取仓库贡献者的详细统计信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/contributors/statistic?access_token=YOUR_TOKEN
```

---

### 12. 下载次数统计

> 详细文档: [get-download-statistics.md](Repositories/get-download-statistics.md)

获取仓库的下载次数统计。

**请求示例**:
```bash
GET /repos/:owner/:repo/download_statistics?access_token=YOUR_TOKEN&start_date=2024-01-01&end_date=2024-12-31
```

---

### 13. 获取仓库动态

> 详细文档: [get-repo-events.md](Repositories/get-repo-events.md)

获取仓库的事件动态。

**请求示例**:
```bash
GET /repos/:owner/:repo/events?access_token=YOUR_TOKEN
```

---

### 14. 设置项目模块

> 详细文档: [update-module-setting.md](Repositories/update-module-setting.md)

设置仓库的模块功能。

**请求示例**:
```bash
PUT /repos/:owner/:repo/module/setting?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "has_wiki": true,
  "has_issue": true,
  "has_fork": true
}
```

---

### 15. 更新仓库设置

> 详细文档: [update-repo.md](Repositories/update-repo.md)

更新仓库的基本设置。

**请求示例**:
```bash
PATCH /repos/:owner/:repo?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "name": "new-repo-name",
  "description": "Updated description",
  "private": false
}
```

---

### 16. 删除一个仓库

> 详细文档: [delete-repo.md](Repositories/delete-repo.md)

删除指定的仓库。

**请求示例**:
```bash
DELETE /repos/:owner/:repo?access_token=YOUR_TOKEN
```

---

### 17. 更新仓库设置(高级)

> 详细文档: [update-repo-settings.md](Repositories/update-repo-settings.md)

更新仓库的高级设置。

**请求示例**:
```bash
PUT /repos/:owner/:repo/repo_settings?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "disable_fork": false,
  "forbidden_developer_create_branch": true
}
```

---

### 18. 获取仓库设置

> 详细文档: [get-repo-settings.md](Repositories/get-repo-settings.md)

获取仓库的设置信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/repo_settings?access_token=YOUR_TOKEN
```

---

### 19. 获取 Pull Request设置

> 详细文档: [get-pull-request-settings.md](Repositories/get-pull-request-settings.md)

获取仓库的Pull Request设置。

**请求示例**:
```bash
GET /repos/:owner/:repo/pull_request_settings?access_token=YOUR_TOKEN
```

---

### 20. 更新 Pull Request设置

> 详细文档: [update-pull-request-settings.md](Repositories/update-pull-request-settings.md)

更新仓库的Pull Request设置。

**请求示例**:
```bash
PUT /repos/:owner/:repo/pull_request_settings?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "only_allow_merge_if_all_discussions_are_resolved": true,
  "delete_source_branch_when_merged": true
}
```

---

### 21. 修改项目代码审查设置

> 详细文档: [update-reviewer.md](Repositories/update-reviewer.md)

设置仓库的代码审查配置。

**请求示例**:
```bash
PUT /repos/:owner/:repo/reviewer?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "assignees": "user1,user2",
  "testers": "user3"
}
```

---

### 22. 获取项目的权限模式

> 详细文档: [get-transition.md](Repositories/get-transition.md)

获取仓库的权限模式信息。

**请求示例**:
```bash
GET /repos/:owner/:repo/transition?access_token=YOUR_TOKEN
```

---

### 23. 更新仓库的权限模式

> 详细文档: [update-transition.md](Repositories/update-transition.md)

更新仓库的权限模式。

**请求示例**:
```bash
PUT /repos/:owner/:repo/transition?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "mode": 1
}
```

---

### 24. 设置项目推送规则

> 详细文档: [update-push-config.md](Repositories/update-push-config.md)

设置仓库的推送规则。

**请求示例**:
```bash
PUT /repos/:owner/:repo/push_config?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "deny_force_push": true,
  "max_file_size": 10485760
}
```

---

### 25. 获取项目推送规则

> 详细文档: [get-push-config.md](Repositories/get-push-config.md)

获取仓库的推送规则配置。

**请求示例**:
```bash
GET /repos/:owner/:repo/push_config?access_token=YOUR_TOKEN
```

---

### 26. 更新项目成员角色

> 详细文档: [update-member-role.md](Repositories/update-member-role.md)

更新项目成员的角色权限。

**请求示例**:
```bash
PUT /repos/:owner/:repo/members/:username?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "permission": "push"
}
```

---

### 27. 获取项目自定义角色

> 详细文档: [get-customized-roles.md](Repositories/get-customized-roles.md)

获取项目的自定义角色列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/customized_roles?access_token=YOUR_TOKEN
```

---

### 28. Fork一个仓库

> 详细文档: [fork-repo.md](Repositories/fork-repo.md)

Fork一个仓库到自己的账户或组织。

**请求示例**:
```bash
POST /repos/:owner/:repo/forks?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "organization": "org-name"
}
```

---

### 29. 查看仓库的Forks

> 详细文档: [get-forks.md](Repositories/get-forks.md)

获取仓库的所有Fork列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/forks?access_token=YOUR_TOKEN
```

---

### 30. 仓库转移

> 详细文档: [transfer-repo.md](Repositories/transfer-repo.md)

将仓库转移给其他用户。

**请求示例**:
```bash
POST /repos/:owner/:repo/transfer?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "new_owner": "new-owner"
}
```

---

### 31. 转移仓(组织)

> 详细文档: [org-transfer-repo.md](Repositories/org-transfer-repo.md)

转移组织仓库。

**请求示例**:
```bash
POST /org/:org/projects/:repo/transfer?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "transfer_to": "target-org",
  "password": "your-password"
}
```

---

### 32. 仓库归档

> 详细文档: [archive-repo.md](Repositories/archive-repo.md)

归档或取消归档仓库。

**请求示例**:
```bash
PUT /org/:org/repo/:repo/status?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "status": 1,
  "password": "your-password"
}
```

---

### 33. 上传图片

> 详细文档: [upload-image.md](Repositories/upload-image.md)

上传图片到仓库。

**请求示例**:
```bash
POST /repos/:owner/:repo/img/upload?access_token=YOUR_TOKEN
Content-Type: application/json

{
  "body": "base64-encoded-image",
  "file_name": "image.png"
}
```

---

### 34. 上传文件

> 详细文档: [upload-file.md](Repositories/upload-file.md)

上传文件到仓库。

**请求示例**:
```bash
POST /repos/:owner/:repo/file/upload?access_token=YOUR_TOKEN
```

---

### 35. 列出 watch 了仓库的用户

> 详细文档: [get-subscribers.md](Repositories/get-subscribers.md)

获取关注仓库的用户列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/subscribers?access_token=YOUR_TOKEN
```

---

### 36. 列出 star 了仓库的用户

> 详细文档: [get-stargazers.md](Repositories/get-stargazers.md)

获取Star仓库的用户列表。

**请求示例**:
```bash
GET /repos/:owner/:repo/stargazers?access_token=YOUR_TOKEN
```

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 19个 |
| POST 请求 | 6个 |
| PUT 请求 | 10个 |
| DELETE 请求 | 1个 |
| PATCH 请求 | 1个 |

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
