# 更新项目成员角色

更新项目成员的角色权限。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/members/:username`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-members-username

## 参数说明

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径 |
| username | string | 是 | 成员用户名 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| role | string | 是 | 角色名称(guest/reporter/developer/maintainer/owner) |
| role_id | integer | 否 | 自定义角色ID |
| expires_at | string | 否 | 成员权限过期时间(ISO 8601格式) |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 成员ID |
| username | string | 用户名 |
| name | string | 姓名 |
| email | string | 邮箱 |
| avatar_url | string | 头像URL |
| role | string | 角色名称 |
| role_id | integer | 角色ID |
| access_level | integer | 访问级别 |
| expires_at | string | 过期时间 |
| state | string | 状态 |
| created_at | string | 加入时间 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/members/testuser?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "developer",
    "expires_at": "2024-12-31T23:59:59Z"
  }'
```

## 响应示例

```json
{
  "id": 789,
  "username": "testuser",
  "name": "测试用户",
  "email": "testuser@example.com",
  "avatar_url": "https://gitcode.com/uploads/user/avatar/789/avatar.png",
  "role": "developer",
  "role_id": 30,
  "access_level": 30,
  "expires_at": "2024-12-31T23:59:59Z",
  "state": "active",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [获取项目自定义角色](get-customized-roles.md)
- [获取仓库设置](get-repo-settings.md)
