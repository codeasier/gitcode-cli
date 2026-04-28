# 获取仓库设置

获取仓库的高级设置信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/repo_settings`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-repo-settings

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
| disable_fork | integer | 禁用Fork |
| forbidden_developer_create_branch | integer | 禁止开发者创建分支 |
| forbidden_developer_create_tag | integer | 禁止开发者创建标签 |
| forbidden_committer_create_branch | integer | 禁止提交者创建分支 |
| generate_pre_merge_ref | integer | 生成预合并引用 |
| forbidden_gitlab_access | integer | 禁止GitLab访问 |
| rebase_disable_trigger_webhook | integer | Rebase禁用触发Webhook |
| include_lfs_objects | integer | 包含LFS对象 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/repo_settings?access_token=YOUR_TOKEN"
```

## 响应示例

```json
{
  "disable_fork": 0,
  "forbidden_developer_create_branch": 1,
  "forbidden_developer_create_tag": 0,
  "forbidden_committer_create_branch": 0,
  "generate_pre_merge_ref": 1,
  "forbidden_gitlab_access": 0,
  "rebase_disable_trigger_webhook": 0,
  "include_lfs_objects": 1
}
```

## 相关接口

- [更新仓库设置](update-repo-settings.md)
