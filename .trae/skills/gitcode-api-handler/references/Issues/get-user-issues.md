# 获取授权用户的所有Issues

获取当前授权用户的所有 Issues 列表

## 基本信息

- **方法**: GET
- **路径**: `/user/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-user-issues

## 请求参数

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| filter | string | 否 | 筛选参数: assigned(授权用户负责的), created(授权用户创建的), all(包含前两者的)。默认: assigned |
| state | string | 否 | Issue的状态: open(开启的), progressing(进行中), closed(关闭的), rejected(拒绝的)。默认: open |
| labels | string | 否 | 用逗号分开的标签。如: bug,performance |
| sort | string | 否 | 排序依据: created(创建时间), updated_at(更新时间)。默认: created_at |
| direction | string | 否 | 排序方式: asc(升序), desc(降序)。默认: desc |
| since | string | 否 | 起始的更新时间,要求时间格式为 ISO 8601 |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量,最大为 100,默认 20 |
| schedule | string | 否 | 计划开始日期,格式:20181006T173008+80-20181007T173008+80(区间),或者 -20181007T173008+80(小于20181007T173008+80),或者 20181006T173008+80-(大于20181006T173008+80),要求时间格式为20181006T173008+80 |
| deadline | string | 否 | 计划截止日期,格式同上 |
| created_at | string | 否 | 任务创建时间,格式同上 |
| finished_at | string | 否 | 任务完成时间,即任务最后一次转为已完成状态的时间点。格式同上 |

## 响应

### 响应结构

返回 Issue 对象数组,每个对象包含以下字段:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | integer | Issue ID |
| html_url | string | Issue的HTML URL |
| number | string | Issue编号 |
| state | string | Issue状态 |
| title | string | Issue标题 |
| body | string | Issue内容 |
| assignee | object | 指派人信息 |
| repository | object | 仓库信息 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| labels | array | 标签列表 |
| comments | integer | 评论数 |
| priority | integer | 优先级 |
| depth | integer | 深度 |
| parent_id | integer | 父Issue ID |
| milestone | object | 里程碑信息 |
| visibility_reason | string | 可见性,public:公开可见,confidential:私密,项目成员可见,other:其他原因导致的仅项目成员可见 |

### 响应示例

```json
[
  {
    "id": 123456,
    "html_url": "https://gitcode.com/owner/repo/issues/1",
    "number": "1",
    "state": "open",
    "title": "我的Issue示例",
    "body": "这是我的Issue内容",
    "assignee": {
      "id": "123",
      "login": "username",
      "name": "用户名"
    },
    "repository": {
      "id": 789,
      "name": "repo",
      "full_name": "owner/repo"
    },
    "created_at": "2024-01-01T10:00:00+08:00",
    "updated_at": "2024-01-01T10:00:00+08:00",
    "labels": [],
    "comments": 0,
    "priority": 1,
    "depth": 0,
    "parent_id": null,
    "milestone": null,
    "visibility_reason": "public"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/user/issues?access_token=YOUR_TOKEN&filter=all&state=open" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/user/issues"
params = {
    "access_token": "YOUR_TOKEN",
    "filter": "all",
    "state": "open"
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
