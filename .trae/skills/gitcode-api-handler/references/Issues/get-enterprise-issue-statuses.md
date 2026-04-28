# 获取企业issue状态

获取企业中所有 Issue 的状态列表

## 基本信息

- **方法**: GET
- **路径**: `/enterprises/:enterprise/issue/statuses`
- **文档URL**: https://docs.gitcode.com/docs/apis/get-api-v-5-enterprises-enterprise-issue-statuses

## 请求参数

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| enterprise | string | 是 | 企业路径(path/login) |

### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | 是 | 用户授权码 |

## 响应

### 响应结构

返回状态对象数组

### 响应示例

```json
[
  {
    "id": 1,
    "name": "开启",
    "color": "28a745"
  },
  {
    "id": 2,
    "name": "进行中",
    "color": "0366d6"
  },
  {
    "id": 3,
    "name": "已关闭",
    "color": "cb2431"
  }
]
```

## 请求示例

### cURL

```bash
curl -X GET "https://api.gitcode.com/api/v5/enterprises/:enterprise/issue/statuses?access_token=YOUR_TOKEN" \
  -H "Accept: application/json"
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/enterprises/my-enterprise/issue/statuses"
params = {"access_token": "YOUR_TOKEN"}
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers, params=params)
print(response.json())
```
