# 获取企业某个Issue所有评论

获取企业中某个 Issue 的所有评论列表

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issues/:number/comments`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issues-number-comments

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| enterprise | string | 是 | 仓库所属空间地址(组织或个人的地址path) |
| number | integer | 是 | issue 全局唯一 id |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量:最大为 100,默认 20 |

## 响应

### 响应结构

返回评论对象数组,每个对象包含以下字段:

| 字段 | 类型 | 描述 |
|------|------|------|
| body | string | 评论内容 |
| created_at | string | 创建时间 |
| id | integer | 评论ID |
| target | object | 目标对象 |
| target.issue | object | Issue信息 |
| target.issue.id | integer | Issue ID |
| target.issue.iid | integer | Issue内部编号 |
| target.issue.title | string | Issue标题 |
| updated_at | string | 更新时间 |
| user | object | 评论用户信息 |
| user.id | integer | 用户ID |
| user.login | string | 用户登录名 |
| user.name | string | 用户名称 |
| user.type | string | 用户类型 |

### 响应示例

```json
[
  {
    "body": "etst",
    "created_at": "2024-12-10T16:02:21+08:00",
    "id": 1535981,
    "target": {
      "issue": {
        "id": 471521,
        "iid": 1,
        "title": "bbbbb"
      }
    },
    "updated_at": "2024-12-10T16:02:21+08:00",
    "user": {
      "id": 287,
      "login": "csdn_fenglh",
      "name": "fenglh",
      "type": "User"
    }
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues/:number/comments?access_token=YOUR_TOKEN&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/my-enterprise/issues/471521/comments"
params = {
    "access_token": "YOUR_TOKEN",
    "per_page": 20
}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
