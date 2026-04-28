# 获取企业某个Issue所有标签

获取企业中某个 Issue 的所有标签列表

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issues/:issue_id/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issues-issue-id-labels

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| enterprise | string | 是 | 企业路径(path/login) |
| issue_id | string | 是 | Issue ID |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 当前的页码 |
| per_page | integer | 否 | 每页的数量 |

## 响应

### 响应结构

返回标签对象数组

### 响应示例

```json
[
  {
    "id": 1,
    "name": "bug",
    "color": "ff0000",
    "description": "Bug标签"
  },
  {
    "id": 2,
    "name": "enhancement",
    "color": "00ff00",
    "description": "功能增强"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issues/:issue_id/labels?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/my-enterprise/issues/123/labels"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
