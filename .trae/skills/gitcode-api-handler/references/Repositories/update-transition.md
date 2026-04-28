# 更新仓库的权限模式

更新仓库的权限模式配置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/transition`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-transition

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
| transition_mode | string | 是 | 权限模式(private/public/internal) |
| visibility | string | 否 | 可见性级别 |
| access_level | integer | 否 | 访问级别(0-50) |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| transition_mode | string | 权限模式 |
| visibility | string | 可见性级别 |
| access_level | integer | 访问级别 |
| permissions | object | 权限配置 |
| permissions.read | boolean | 读取权限 |
| permissions.write | boolean | 写入权限 |
| permissions.admin | boolean | 管理权限 |
| message | string | 操作结果消息 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/transition?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transition_mode": "private",
    "visibility": "private",
    "access_level": 30
  }'
```

## 响应示例

```json
{
  "transition_mode": "private",
  "visibility": "private",
  "access_level": 30,
  "permissions": {
    "read": true,
    "write": true,
    "admin": false
  },
  "message": "权限模式更新成功",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [获取项目的权限模式](get-transition.md)
- [更新仓库设置](update-repo-settings.md)
