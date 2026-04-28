# 设置项目模块

设置项目的模块配置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/module/setting`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-module-setting

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

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| module_enabled | boolean | 否 | 是否启用模块功能 |
| module_name | string | 否 | 模块名称 |
| module_description | string | 否 | 模块描述 |
| module_path | string | 否 | 模块路径 |
| module_branch | string | 否 | 模块所在分支 |
| module_visibility | string | 否 | 模块可见性(public/private/internal) |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 模块ID |
| name | string | 模块名称 |
| description | string | 模块描述 |
| path | string | 模块路径 |
| branch | string | 模块所在分支 |
| visibility | string | 模块可见性 |
| enabled | boolean | 是否启用 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/module/setting?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_enabled": true,
    "module_name": "core-module",
    "module_description": "核心功能模块",
    "module_path": "src/core",
    "module_branch": "main",
    "module_visibility": "private"
  }'
```

## 响应示例

```json
{
  "id": 123,
  "name": "core-module",
  "description": "核心功能模块",
  "path": "src/core",
  "branch": "main",
  "visibility": "private",
  "enabled": true,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [获取仓库设置](get-repo-settings.md)
- [更新仓库设置](update-repo-settings.md)
