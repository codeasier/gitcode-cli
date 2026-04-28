# 获取项目自定义角色

获取项目的自定义角色列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/customized_roles`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-customized-roles

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
| page | integer | 否 | 页码，默认为1 |
| per_page | integer | 否 | 每页数量，默认为20，最大100 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 角色ID |
| name | string | 角色名称 |
| description | string | 角色描述 |
| color | string | 角色颜色标识 |
| base_access_level | integer | 基础访问级别 |
| permissions | array | 权限列表 |
| permissions[].name | string | 权限名称 |
| permissions[].enabled | boolean | 是否启用 |
| member_count | integer | 使用该角色的成员数量 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/customized_roles?access_token=YOUR_TOKEN&page=1&per_page=20"
```

## 响应示例

```json
[
  {
    "id": 101,
    "name": "代码审查员",
    "description": "负责代码审查的成员角色",
    "color": "#4CAF50",
    "base_access_level": 30,
    "permissions": [
      {
        "name": "read_code",
        "enabled": true
      },
      {
        "name": "write_code",
        "enabled": false
      },
      {
        "name": "review_merge_request",
        "enabled": true
      },
      {
        "name": "manage_issues",
        "enabled": true
      }
    ],
    "member_count": 5,
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-15T14:30:00Z"
  },
  {
    "id": 102,
    "name": "测试工程师",
    "description": "负责测试相关工作的角色",
    "color": "#2196F3",
    "base_access_level": 20,
    "permissions": [
      {
        "name": "read_code",
        "enabled": true
      },
      {
        "name": "write_code",
        "enabled": false
      },
      {
        "name": "manage_issues",
        "enabled": true
      },
      {
        "name": "run_pipeline",
        "enabled": true
      }
    ],
    "member_count": 3,
    "created_at": "2024-01-02T10:00:00Z",
    "updated_at": "2024-01-16T09:00:00Z"
  }
]
```

## 相关接口

- [更新项目成员角色](update-member-role.md)
- [获取仓库设置](get-repo-settings.md)
