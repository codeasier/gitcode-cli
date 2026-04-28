# 删除一个仓库

删除指定的仓库。

## 基本信息

- **方法**: DELETE
- **路径**: `/repos/:owner/:repo`
- **文档URL**: https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo

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

无内容(204 No Content)

## 请求示例

```bash
curl -X DELETE "https://api.gitcode.com/api/v5/repos/:owner/:repo?access_token=YOUR_TOKEN"
```

## 注意事项

⚠️ **警告**: 此操作不可逆,删除后仓库将无法恢复!

## 相关接口

- [更新仓库设置](update-repo.md)
- [仓库归档](archive-repo.md)
