# 下载次数统计

获取指定仓库的下载次数统计信息。

## 基本信息

- **方法**: GET
- **路径**: `/repos/:owner/:repo/download_statistics`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-download-statistics

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
| start_date | string | 否 | 统计起始日期包含当前日期(eg:2024-01-06) |
| end_date | string | 否 | 统计截止日期包含当前日期(eg:2024-12-06) |
| direction | string | 否 | 排序方式:升序,降序。默认:desc |

## 响应字段

| 字段名 | 类型 | 描述 |
|--------|------|------|
| download_statistics_detail | array | 下载统计详情数组 |
| download_statistics_total | integer | 下载统计总数 |
| download_statistics_history_total | integer | 历史下载统计总数 |

## 请求示例

```bash
curl -X GET "https://api.gitcode.com/api/v5/repos/:owner/:repo/download_statistics?access_token=YOUR_TOKEN&start_date=2024-01-01&end_date=2024-12-31&direction=desc"
```

## 响应示例

```json
{
  "download_statistics_detail": [
    {
      "date": "2024-01-15",
      "count": 123
    },
    {
      "date": "2024-01-16",
      "count": 145
    },
    {
      "date": "2024-01-17",
      "count": 98
    }
  ],
  "download_statistics_total": 366,
  "download_statistics_history_total": 15234
}
```

## 相关接口

- [获取仓库贡献者统计信息](get-contributors-statistic.md)
- [获取仓库贡献者](get-contributors.md)
