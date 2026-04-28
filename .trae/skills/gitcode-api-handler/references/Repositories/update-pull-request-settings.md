# 更新 Pull Request设置

更新仓库的Pull Request相关设置。

## 基本信息

- **方法**: PUT
- **路径**: `/repos/:owner/:repo/pull_request_settings`
- **文档URL**: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pull-request-settings

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
| approval_required_reviewers_enable | boolean | 否 | 启用审批所需评审者 |
| approval_required_reviewers | integer | 否 | 审批所需评审者数量 |
| only_allow_merge_if_all_discussions_are_resolved | boolean | 否 | 仅当所有讨论已解决时允许合并 |
| only_allow_merge_if_pipeline_succeeds | boolean | 否 | 仅当流水线成功时允许合并 |
| disable_merge_by_self | boolean | 否 | 禁用自己合并 |
| can_force_merge | boolean | 否 | 允许强制合并 |
| add_notes_after_merged | boolean | 否 | 合并后添加备注 |
| mark_auto_merged_mr_as_closed | boolean | 否 | 将自动合并的MR标记为已关闭 |
| can_reopen | boolean | 否 | 允许重新打开 |
| delete_source_branch_when_merged | boolean | 否 | 合并时删除源分支 |
| disable_squash_merge | boolean | 否 | 禁用Squash合并 |
| auto_squash_merge | boolean | 否 | 自动Squash合并 |
| merge_method | string | 否 | 合并方法 |
| squash_merge_with_no_merge_commit | boolean | 否 | Squash合并不含合并提交 |
| merged_commit_author | string | 否 | 合并提交作者 |
| approval_required_approvers | integer | 否 | 审批所需批准者数量 |
| approval_approver_ids | string | 否 | 审批批准者ID |
| approval_tester_ids | string | 否 | 审批测试者ID |
| approval_required_testers | integer | 否 | 审批所需测试者数量 |
| is_check_cla | boolean | 否 | 是否检查CLA |
| is_allow_lite_merge_request | boolean | 否 | 是否允许轻量合并请求 |
| lite_merge_request_prefix_title | string | 否 | 轻量合并请求前缀标题 |
| close_issue_when_mr_merged | boolean | 否 | MR合并时关闭Issue |

## 响应字段

返回更新后的PR设置。

## 请求示例

```bash
curl -X PUT "https://api.gitcode.com/api/v5/repos/:owner/:repo/pull_request_settings?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "only_allow_merge_if_all_discussions_are_resolved": true,
    "delete_source_branch_when_merged": true,
    "merge_method": "squash"
  }'
```

## 相关接口

- [获取 Pull Request设置](get-pull-request-settings.md)
