# 获取仓库的语言

获取指定仓库使用的编程语言统计信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/languages`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-languages

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

返回语言统计对象,格式为 `{ "语言名": 代码字节数 }`。

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/languages?access_token=YOUR_TOKEN"
```

## 响应示例

```json
{
  "JavaScript": 123456,
  "TypeScript": 98765,
  "Python": 45678,
  "HTML": 12345,
  "CSS": 8765
}
```

## 相关接口

- [获取仓库贡献者](get-contributors.md)
- [获取仓库贡献者统计信息](get-contributors-statistic.md)
