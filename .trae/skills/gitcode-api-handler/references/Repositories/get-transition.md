# 获取项目的权限模式

获取项目的权限模式配置信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/transition`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-transition

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

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| transition_mode | string | 权限模式(private/public/internal) |
| visibility | string | 可见性级别 |
| access_level | integer | 访问级别 |
| permissions | object | 权限配置 |
| permissions.read | boolean | 读取权限 |
| permissions.write | boolean | 写入权限 |
| permissions.admin | boolean | 管理权限 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/transition?access_token=YOUR_TOKEN"
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
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [更新仓库的权限模式](update-transition.md)
- [获取仓库设置](get-repo-settings.md)
