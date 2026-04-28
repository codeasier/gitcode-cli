# 更新仓库设置

更新仓库的高级设置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/repo_settings`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-repo-settings

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
| disable_fork | boolean | 否 | 禁用Fork |
| forbidden_developer_create_branch | boolean | 否 | 禁止开发者创建分支 |
| forbidden_developer_create_tag | boolean | 否 | 禁止开发者创建标签 |
| forbidden_committer_create_branch | boolean | 否 | 禁止提交者创建分支 |
| forbidden_developer_create_branch_user_ids | string | 否 | 禁止创建分支的开发者用户ID |
| branch_name_regex | string | 否 | 分支名称正则表达式 |
| tag_name_regex | string | 否 | 标签名称正则表达式 |
| generate_pre_merge_ref | boolean | 否 | 生成预合并引用 |
| rebase_disable_trigger_webhook | boolean | 否 | Rebase禁用触发Webhook |
| open_gpg_verified | boolean | 否 | 开启GPG验证 |
| include_lfs_objects | boolean | 否 | 包含LFS对象 |

## 响应字段

返回更新后的设置。

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/repo_settings?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "disable_fork": false,
    "forbidden_developer_create_branch": true,
    "branch_name_regex": "^(feature|bugfix|hotfix)/.*$"
  }'
```

## 相关接口

- [获取仓库设置](get-repo-settings.md)
- [更新仓库设置(基础)](update-repo.md)
