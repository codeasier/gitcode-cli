# 更新仓库设置

更新指定仓库的基本设置信息。

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo

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
| name | string | 否 | 仓库名称 |
| description | string | 否 | 仓库描述 |
| homepage | string | 否 | 主页URL |
| path | string | 否 | 仓库路径 |
| private | boolean | 否 | 是否私有 |
| default_branch | string | 否 | 默认分支 |
| lfs_enabled | boolean | 否 | 是否启用LFS |
| tags | array | 否 | 标签数组 |

## 响应字段

返回更新后的仓库信息。

## 请求示例

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new-repo-name",
    "description": "Updated description",
    "private": false
  }'
```

## 响应示例

```json
{
  "id": 123456,
  "name": "new-repo-name",
  "path": "new-repo-name",
  "description": "Updated description",
  "private": false,
  "default_branch": "master"
}
```

## 相关接口

- [删除一个仓库](delete-repo.md)
- [获取仓库设置](get-repo-settings.md)
- [更新仓库设置(高级)](update-repo-settings.md)
