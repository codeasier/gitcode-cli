# 获取仓库贡献者

获取指定仓库的贡献者列表。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/contributors`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contributors

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
| type | string | 否 | 贡献者类型 |

## 响应字段

返回贡献者数组,每个元素包含贡献者的基本信息。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/contributors?access_token=YOUR_TOKEN"
```

## 响应示例

```json
[
  {
    "id": 12345,
    "login": "johndoe",
    "name": "John Doe",
    "avatar_url": "https://gitcode.com/avatars/johndoe",
    "html_url": "https://gitcode.com/johndoe",
    "type": "User",
    "contributions": 42
  },
  {
    "id": 67890,
    "login": "janedoe",
    "name": "Jane Doe",
    "avatar_url": "https://gitcode.com/avatars/janedoe",
    "html_url": "https://gitcode.com/janedoe",
    "type": "User",
    "contributions": 28
  }
]
```

## 相关接口

- [获取仓库的语言](get-languages.md)
- [获取仓库贡献者统计信息](get-contributors-statistic.md)
