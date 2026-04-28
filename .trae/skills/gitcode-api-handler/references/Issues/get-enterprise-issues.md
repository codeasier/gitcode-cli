# 获取某个企业的所有Issues

获取企业中所有的 Issues 列表

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issues`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issues

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| enterprise | string | 是 | 企业的路径(path/login) |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| state | string | 否 | Issue的状态: open(开启的), closed(关闭的), all(所有) 默认: open |
| labels | string | 否 | 用逗号分开的标签。如: bug,performance |
| sort | string | 否 | 排序依据: created(创建时间), updated_at(更新时间)。默认: created_at |
| direction | string | 否 | 排序方式: asc(升序), desc(降序)。默认: desc |
| since | string | 否 | 起始的更新时间,要求时间格式为 ISO 8601 |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量,最大为 100,默认 20 |
| milestone | string | 否 | 根据里程碑标题。none为没里程碑的,*为所有带里程碑的 |
| assignee | string | 否 | 用户的username。 none为没指派者, *为所有带有指派者的 |
| creator | string | 否 | 创建Issues的用户username |
| program | string | 否 | 所属项目名称。none为没所属有项目的,*为所有带所属项目的 |
| created_at | string | 否 | 任务创建日期,格式2024-11-09 |
| created_before | string | 否 | 任务创建截止时间,格式2024-11-09 |
| search | string | 否 | 通过关键字搜索issue标题或者内容 |

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
| user | object | 创建者信息 |
| repository | object | 仓库信息 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| finished_at | string | 完成时间 |
| deadline | string | 截止时间 |
| labels | array | 标签列表 |
| issue_state | string | Issue状态 |
| comments | integer | 评论数 |
| priority | integer | 优先级 |
| issue_type | string | Issue类型 |
| issue_state_detail | object | Issue状态详情 |
| issue_type_detail | object | Issue类型详情 |
| issue_priority_detail | object | Issue优先级详情 |
| parent_id | integer | 父Issue ID |
| milestone | object | 里程碑信息 |
| url | string | API URL |
| repository_url | string | 仓库API URL |
| assignee | object | 指派人信息 |
| visibility_reason | string | 可见性,public:公开可见,confidential:私密,项目成员可见,other:其他原因导致的仅项目成员可见 |

### 响应示例

```json
[
  {
    "id": 123456,
    "html_url": "https://gitcode.com/owner/repo/issues/1",
    "number": "1",
    "state": "open",
    "title": "企业Issue示例",
    "body": "这是企业Issue的内容",
    "user": {
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
    "finished_at": null,
    "deadline": "2024-12-31T23:59:59+08:00",
    "labels": [],
    "issue_state": "open",
    "comments": 0,
    "priority": 1,
    "issue_type": "task",
    "issue_state_detail": {
      "id": 1,
      "name": "开启"
    },
    "issue_type_detail": {
      "id": 1,
      "name": "任务"
    },
    "issue_priority_detail": {
      "id": 1,
      "name": "高"
    },
    "parent_id": null,
    "milestone": null,
    "url": "https://api.gitcode.com/api/v5/repos/owner/repo/issues/1",
    "repository_url": "https://api.gitcode.com/api/v5/repos/owner/repo",
    "assignee": null,
    "visibility_reason": "public"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues?access_token=YOUR_TOKEN&state=open&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/my-enterprise/issues"
params = {
    "access_token": "YOUR_TOKEN",
    "state": "open",
    "per_page": 20
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
