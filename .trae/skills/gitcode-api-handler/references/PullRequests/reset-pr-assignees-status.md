# 重置 Pull Request审查 的状态

重置 Pull Request审查 的状态

## 基本信息

- **方法**: PATCH
- **路径**: `/repos/:owner/:repo/pulls/:number/assignees`
- **文档URL**: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-number-assignees

## 请求参数

### 路径参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| owner | string | 是 | 仓库所属空间地址(企业、组织或个人的地址path) |
| repo | string | 是 | 仓库路径(path) |
| number | integer | 是 | 第几个PR，即本仓库PR的序数 |

### 查询参数

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| access_token | string | 是 | 用户授权码 |

### 请求体

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| reset_all | boolean | 否 | 是否重置所有审查状态 |

## 响应

### 响应结构

| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | integer | Pull Request ID |
| iid | integer | Pull Request序号 |
| number | integer | Pull Request编号 |
| title | string | Pull Request标题 |
| state | string | Pull Request状态 |

### 响应示例

```json
{
  "id": 100,
  "iid": 1,
  "number": 1,
  "title": "新增功能",
  "state": "open"
}
```

## 请求示例

### cURL

```bash
curl -X PATCH "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/assignees?access_token=YOUR_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "reset_all": true
  }'
```

### Python

```python
import requests

url = "https://api.gitcode.com/api/v5/repos/:owner/:repo/pulls/:number/assignees"
params = {"access_token": "YOUR_TOKEN"}
data = {"reset_all": True}

response = requests.patch(url, params=params, json=data)
print(response.json())
```
