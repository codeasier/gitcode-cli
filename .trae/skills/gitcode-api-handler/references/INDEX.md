# GitCode API 文档索引

本索引提供了 GitCode API 各类操作接口的渐进式文档导航，便于快速查找和获取详细的 API 请求信息。

## 基础信息

- **API 基础URL**: <https://api.gitcode.com/api/v5>
- **文档基础URL**: <https://docs.gitcode.com>
- **认证方式**: OAuth2 Token (access\_token)
- **总接口数量**: 154 个

## API 分类概览

| 分类                | 接口数量 | 主要功能                     | 详细文档                               |
| :---------------- | :--- | :----------------------- | :--------------------------------- |
| **Pull Requests** | 44 个 | PR 创建、合并、评论、测试、审查等完整流程管理 | [PullRequests.md](PullRequests.md) |
| **Repositories**  | 36 个 | 仓库文件操作、设置管理、权限控制、Fork转移等 | [Repositories.md](Repositories.md) |
| **Issues**        | 26 个 | Issue 创建、查询、评论、标签、关联等操作  | [Issues.md](Issues.md)             |
| **Commit**        | 12 个 | 提交查询、评论管理、代码统计、差异对比      | [Commit.md](Commit.md)             |
| **Labels**        | 9 个  | 标签创建、更新、删除及企业和仓库标签管理     | [Labels.md](Labels.md)             |
| **Branch**        | 8 个  | 分支创建、删除、保护规则管理           | [Branch.md](Branch.md)             |
| **Tag**           | 8 个  | 标签创建、删除、保护标签规则管理         | [Tag.md](Tag.md)                   |
| **Release**       | 8 个  | Release 创建、更新、查询、附件管理    | [Release.md](Release.md)           |
| **Search**        | 3 个  | 用户、仓库、Issue 搜索功能         | [Search.md](Search.md)             |

## 详细分类说明

### 1. Pull Requests API

**接口数量**: 44 个

**主要功能模块**:

- **PR 基本操作** (6个): 创建、查询、更新、合并 PR
- **评论管理** (7个): 评论的增删改查、回复、解决状态
- **文件与提交** (4个): 文件列表、变更信息、Commit 信息
- **标签管理** (4个): PR 标签的创建、查询、替换、删除
- **Issue 关联** (3个): PR 与 Issue 的关联管理
- **测试与审查** (3个): 测试流程、审查流程、操作日志
- **人员管理** (10个): 测试人、审查人、评审人的指派与管理
- **表态与历史** (4个): 表态列表、修改历史
- **企业与组织** (3个): 企业和组织级别的 PR 管理

**快速链接**: [PullRequests.md](PullRequests.md) | [详细接口目录](PullRequests/)

***

### 2. Repositories API

**接口数量**: 36 个

**主要功能模块**:

- **文件操作** (8个): 文件的增删改查、目录树、Blob、Raw 文件
- **仓库信息** (5个): 语言统计、贡献者、下载统计、仓库动态
- **仓库设置** (7个): 模块设置、仓库设置、PR 设置
- **权限与审查** (7个): 代码审查、权限模式、推送规则、成员角色
- **Fork 与转移** (5个): Fork 仓库、仓库转移、归档
- **上传功能** (2个): 图片上传、文件上传
- **Star 与 Watch** (2个): Star 用户列表、Watch 用户列表

**快速链接**: [Repositories.md](Repositories.md) | [详细接口目录](Repositories/)

***

### 3. Issues API

**接口数量**: 26 个

**主要功能模块**:

- **Issue 基本操作** (4个): 创建、更新、查询 Issue
- **评论操作** (6个): 评论的增删改查
- **标签操作** (3个): 标签管理
- **关联操作** (3个): PR 和分支关联
- **历史记录** (3个): 操作日志和修改历史
- **表态操作** (2个): 点赞等表态功能
- **企业/组织 Issue** (5个): 企业和组织级别的 Issue 管理

**快速链接**: [Issues.md](Issues.md) | [详细接口目录](Issues/)

***

### 4. Commit API

**接口数量**: 12 个

**主要功能模块**:

- **提交查询** (3个): 获取提交列表、单个提交、提交对比
- **评论管理** (6个): 创建、删除、更新、查询评论
- **统计与导出** (3个): 代码量贡献、Diff、Patch

**快速链接**: [Commit.md](Commit.md) | [详细接口目录](Commit/)

***

### 5. Labels API

**接口数量**: 9 个

**主要功能模块**:

- **仓库标签管理** (5个): 标签的增删改查、批量替换
- **Issue 标签管理** (2个): Issue 标签的替换和删除
- **企业标签管理** (2个): 企业标签的查询（v5 和 v8 版本）

**快速链接**: [Labels.md](Labels.md) | [详细接口目录](Labels/)

***

### 6. Branch API

**接口数量**: 8 个

**主要功能模块**:

- **分支基础操作** (4个): 分支的创建、删除、查询
- **保护分支规则** (4个): 保护规则的创建、删除、查询、更新

**快速链接**: [Branch.md](Branch.md) | [详细接口目录](Branch/)

***

### 7. Tag API

**接口数量**: 8 个

**主要功能模块**:

- **标签基础操作** (3个): 标签的创建、删除、查询
- **保护标签规则** (5个): 保护标签规则的创建、删除、查询、更新

**快速链接**: [Tag.md](Tag.md) | [详细接口目录](Tag/)

***

### 8. Release API

**接口数量**: 8 个

**主要功能模块**:

- **Release 基础操作** (6个): Release 的创建、更新、查询
- **附件管理** (2个): 附件上传地址获取、附件下载

**快速链接**: [Release.md](Release.md) | [详细接口目录](Release/)

***

### 9. Search API

**接口数量**: 3 个

**主要功能模块**:

- **搜索用户** (1个): 根据关键字搜索用户
- **搜索 Issues** (1个): 搜索 Issues 和 Pull Requests
- **搜索仓库** (1个): 根据关键字搜索仓库

**快速链接**: [Search.md](Search.md) | [详细接口目录](Search/)

***

## HTTP 方法统计

| HTTP 方法 | 接口数量 | 主要用途    |
| :------ | :--- | :------ |
| GET     | 81 个 | 查询和获取数据 |
| POST    | 18 个 | 创建资源    |
| PUT     | 21 个 | 更新或替换资源 |
| PATCH   | 7 个  | 部分更新资源  |
| DELETE  | 11 个 | 删除资源    |

## 认证说明

所有 API 接口都需要通过 `access_token` 参数进行认证。支持以下认证方式：

1. **查询参数**: `?access_token={your-token}`
2. **请求头**: `Authorization: Bearer {your-token}`
3. **请求头**: `PRIVATE-TOKEN: {your-token}`

## 分页说明

大多数列表查询接口支持分页，通过以下参数控制：

- `page`: 当前页码，从 1 开始
- `per_page`: 每页数量，最大为 100，默认为 20

## 响应格式

所有接口返回 JSON 格式数据，包含以下通用字段：

- `id`: 资源唯一标识
- `created_at`: 创建时间 (ISO 8601 格式)
- `updated_at`: 更新时间 (ISO 8601 格式)

## 错误处理

API 返回标准 HTTP 状态码：

| 状态码 | 描述 |
|--------|------|
| `200 OK` | GET、PUT 或 DELETE 请求成功，资源以 JSON 形式返回 |
| `201 Created` | POST 请求成功，新创建的资源以 JSON 形式返回 |
| `202 Accepted` | 请求成功，资源计划进行处理 |
| `204 No Content` | 服务器成功处理请求，无返回内容 |
| `301 Moved Permanently` | 资源已永久移动到 Location 头指定的 URL |
| `304 Not Modified` | 资源自上次请求以来未被修改 |
| `400 Bad Request` | 请求参数错误，缺少必需属性 |
| `401 Unauthorized` | 未授权或 token 无效 |
| `403 Forbidden` | 无权限访问该资源 |
| `404 Not Found` | 资源不存在或无权访问 |
| `405 Method Not Allowed` | 不支持的请求方法 |
| `409 Conflict` | 资源冲突（如创建已存在的同名资源） |
| `412 Precondition Failed` | 前置条件失败 |
| `422 Unprocessable Entity` | 请求格式正确但语义错误 |
| `429 Too Many Requests` | 超出速率限制（默认 400次/分，4000次/小时） |
| `500 Server Error` | 服务器内部错误 |
| `503 Service Unavailable` | 服务器暂时过载，无法处理请求 |
| `504 Time Out` | 响应超时 |

## 使用建议

### 渐进式学习路径

1. **入门阶段**: 先阅读各分类的总结文档（如 [PullRequests.md](PullRequests.md)），了解该分类的接口概览和主要功能
2. **深入阶段**: 根据需要点击具体接口的详细文档链接，查看完整的请求参数、响应示例和代码示例
3. **实践阶段**: 参考文档中的请求示例，结合实际项目需求进行 API 调用

### 快速查找

- **按功能查找**: 根据你要实现的功能，在"API 分类概览"表格中找到对应的分类
- **按操作类型查找**: 在各分类文档中，接口按功能模块分组，便于快速定位
- **按 HTTP 方法查找**: 参考各文档中的"统计信息"部分，了解接口的 HTTP 方法分布

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
- [OAuth 认证文档](https://docs.gitcode.com/docs/oauth)

## 文档更新

- **生成时间**: 2024年
- **文档版本**: v1.0
- **API 版本**: v5

