# Search 接口文档

从 GitCode API 文档中提取的 Search 分类下的所有接口文档。

## 基础信息

- **文档基础URL**: https://docs.gitcode.com
- **API基础URL**: https://api.gitcode.com/api/v5
- **接口总数**: 3个

## 接口列表

### 搜索接口

| 序号 | 接口名称 | 方法 | 路径 | 文档链接 |
|------|----------|------|------|----------|
| 1 | 搜索用户 | GET | `/search/users` | [详细文档](Search/search-users.md) |
| 2 | 搜索 Issues | GET | `/search/issues` | [详细文档](Search/search-issues.md) |
| 3 | 搜索仓库 | GET | `/search/repositories` | [详细文档](Search/search-repositories.md) |

## 接口概览

### 1. 搜索用户

> 详细文档: [search-users.md](Search/search-users.md)

根据关键字搜索用户信息。

**请求示例**:
```bash
GET /search/users?q=octocat&sort=followers&order=desc&page=1&per_page=20
```

**支持的排序字段**:
- `best_match` - 最佳匹配（默认）
- `followers` - 粉丝数
- `repositories` - 仓库数
- `joined` - 加入时间

---

### 2. 搜索 Issues

> 详细文档: [search-issues.md](Search/search-issues.md)

根据关键字搜索 Issues 和 Pull Requests。

**请求示例**:
```bash
GET /search/issues?q=bug+state:open+repo:owner/repo&sort=created&order=desc&page=1&per_page=20
```

**支持的排序字段**:
- `best_match` - 最佳匹配（默认）
- `created` - 创建时间
- `updated` - 更新时间
- `comments` - 评论数

**常用搜索限定符**:
| 限定符 | 示例 | 说明 |
|--------|------|------|
| type | `type:issue` / `type:pr` | 指定搜索类型 |
| state | `state:open` / `state:closed` | 指定状态 |
| author | `author:username` | 指定作者 |
| repo | `repo:owner/repo` | 指定仓库 |
| label | `label:bug` | 指定标签 |

---

### 3. 搜索仓库

> 详细文档: [search-repositories.md](Search/search-repositories.md)

根据关键字搜索仓库信息。

**请求示例**:
```bash
GET /search/repositories?q=python+stars:>100+language:python&sort=stars&order=desc&page=1&per_page=20
```

**支持的排序字段**:
- `best_match` - 最佳匹配（默认）
- `stars` - Star 数量
- `forks` - Fork 数量
- `updated` - 更新时间

**常用搜索限定符**:
| 限定符 | 示例 | 说明 |
|--------|------|------|
| user | `user:username` | 指定用户/组织 |
| language | `language:python` | 指定编程语言 |
| stars | `stars:>100` | 指定 star 数量 |
| topic | `topic:api` | 指定主题 |
| license | `license:mit` | 指定许可证 |
| is | `is:public` / `is:private` | 指定可见性 |

---

## 统计信息

| 请求类型 | 数量 |
|----------|------|
| GET 请求 | 3个 |
| POST 请求 | 0个 |
| PUT 请求 | 0个 |
| DELETE 请求 | 0个 |

## 公共特性

### 响应结构

所有搜索接口返回统一的响应结构：

```json
{
  "total_count": 123,
  "incomplete_results": false,
  "items": [...]
}
```

| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_count | integer | 搜索结果总数 |
| incomplete_results | boolean | 结果是否不完整（超时时为 true） |
| items | array | 搜索结果列表 |

### 通用参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| q | string | 是 | 搜索关键字，支持搜索限定符 |
| sort | string | 否 | 排序字段 |
| order | string | 否 | 排序顺序（asc/desc），默认 desc |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认20，最大100 |

### 搜索限定符语法

搜索限定符可以组合使用，用空格分隔：

```
q=keyword+qualifier1:value1+qualifier2:value2
```

示例：
```
q=api+language:python+stars:>100+is:public
```

## 参考链接

- [GitCode API 官方文档](https://docs.gitcode.com/docs/apis/)
- [GitCode 帮助文档](https://docs.gitcode.com/)
