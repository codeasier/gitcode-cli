# 获取 Pull Request设置

获取仓库的Pull Request相关设置。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/pull_request_settings`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pull-request-settings

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
| merge_request_setting | object | 合并请求设置对象 |
| └─ only_allow_merge_if_all_discussions_are_resolved | boolean | 仅当所有讨论已解决时允许合并 |
| └─ only_allow_merge_if_pipeline_succeeds | boolean | 仅当流水线成功时允许合并 |
| └─ merge_method | string | 合并方法 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/pull_request_settings?access_token=YOUR_TOKEN"
```

## 响应示例

```json
{
  "merge_request_setting": {
    "only_allow_merge_if_all_discussions_are_resolved": true,
    "only_allow_merge_if_pipeline_succeeds": false,
    "merge_method": "merge"
  }
}
```

## 相关接口

- [更新 Pull Request设置](update-pull-request-settings.md)
