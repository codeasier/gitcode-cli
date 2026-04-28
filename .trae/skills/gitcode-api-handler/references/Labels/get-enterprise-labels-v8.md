# 获取标签列表

获取指定企业的标签列表（API v8版本）。

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/labels`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-8-enterprises-enterprise-labels

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| enterprise | string | 是 | 企业路径(path) |

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

## 响应

### 响应结构 (array)

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | integer | 标签ID |
| name | string | 标签名称 |
| color | string | 标签颜色（十六进制） |
| description | string | 标签描述 |
| repositories_count | integer | 使用该标签的仓库数量 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 响应示例

```json
[
  {
    "id": 1,
    "name": "critical",
    "color": "b60205",
    "description": "Critical priority issues",
    "repositories_count": 15,
    "created_at": "2024-01-01T10:00:00.000+08:00",
    "updated_at": "2024-01-15T14:30:00.000+08:00"
  },
  {
    "id": 2,
    "name": "security",
    "color": "d93f0b",
    "description": "Security related issues",
    "repositories_count": 8,
    "created_at": "2024-01-02T09:00:00.000+08:00",
    "updated_at": "2024-01-20T16:45:00.000+08:00"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v8/enterprises/:enterprise/labels?access_token=YOUR_TOKEN&page=1&per_page=20" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v8/enterprises/my-enterprise/labels"
params = {
    "access_token": "YOUR_TOKEN",
    "page": 1,
    "per_page": 20
}

response = requests.get(url, params=params)
print(response.json())
```
