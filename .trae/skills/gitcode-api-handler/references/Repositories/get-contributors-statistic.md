# 获取仓库贡献者统计信息

获取指定仓库的贡献者详细统计信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/contributors/statistic`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contributors-statistic

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
| author | string | 否 | 作者 |
| current_user | string | 否 | 当前用户 |
| since | string | 否 | 起始时间 |
| until | string | 否 | 结束时间 |
| ref_name | string | 否 | 分支名 |

## 响应字段

返回贡献者统计信息,包含提交次数、代码行数变更等详细数据。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/contributors/statistic?access_token=YOUR_TOKEN&since=2024-01-01&until=2024-12-31"
```

## 响应示例

```json
[
  {
    "author": {
      "id": 12345,
      "login": "johndoe",
      "name": "John Doe",
      "email": "john@example.com",
      "avatar_url": "https://gitcode.com/avatars/johndoe"
    },
    "total": 42,
    "weeks": [
      {
        "w": 1704067200,
        "a": 1234,
        "d": 567,
        "c": 10
      }
    ]
  }
]
```

## 相关接口

- [获取仓库的语言](get-languages.md)
- [获取仓库贡献者](get-contributors.md)
