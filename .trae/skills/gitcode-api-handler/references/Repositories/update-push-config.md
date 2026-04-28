# 设置项目推送规则

设置项目的推送规则配置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/push_config`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-push-config

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
| commit_message_regex | string | 否 | 提交消息正则表达式 |
| commit_message_negative_regex | string | 否 | 提交消息反向正则表达式 |
| branch_name_regex | string | 否 | 分支名称正则表达式 |
| deny_delete_tag | boolean | 否 | 禁止删除标签 |
| deny_force_push | boolean | 否 | 禁止强制推送 |
| commit_committer_check | boolean | 否 | 检查提交者 |
| commit_author_check | boolean | 否 | 检查作者 |
| max_file_size | integer | 否 | 最大文件大小(KB) |
| member_check | boolean | 否 | 检查成员 |
| prevent_secrets | boolean | 否 | 防止提交敏感信息 |
| reject_unsigned_commits | boolean | 否 | 拒绝未签名提交 |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | 推送规则ID |
| commit_message_regex | string | 提交消息正则表达式 |
| commit_message_negative_regex | string | 提交消息反向正则表达式 |
| branch_name_regex | string | 分支名称正则表达式 |
| deny_delete_tag | boolean | 禁止删除标签 |
| deny_force_push | boolean | 禁止强制推送 |
| commit_committer_check | boolean | 检查提交者 |
| commit_author_check | boolean | 检查作者 |
| max_file_size | integer | 最大文件大小(KB) |
| member_check | boolean | 检查成员 |
| prevent_secrets | boolean | 防止提交敏感信息 |
| reject_unsigned_commits | boolean | 拒绝未签名提交 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/push_config?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "commit_message_regex": "^(feat|fix|docs|style|refactor|test|chore): .+",
    "branch_name_regex": "^(feature|bugfix|hotfix|release)/.*$",
    "deny_delete_tag": true,
    "deny_force_push": true,
    "max_file_size": 5120,
    "prevent_secrets": true
  }'
```

## 响应示例

```json
{
  "id": 456,
  "commit_message_regex": "^(feat|fix|docs|style|refactor|test|chore): .+",
  "commit_message_negative_regex": null,
  "branch_name_regex": "^(feature|bugfix|hotfix|release)/.*$",
  "deny_delete_tag": true,
  "deny_force_push": true,
  "commit_committer_check": false,
  "commit_author_check": false,
  "max_file_size": 5120,
  "member_check": false,
  "prevent_secrets": true,
  "reject_unsigned_commits": false,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:00Z"
}
```

## 相关接口

- [获取项目推送规则](get-push-config.md)
- [更新仓库设置](update-repo-settings.md)
