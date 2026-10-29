# Issue 与 PR 的 JSON 输出

create、list 和 view 对结构化输出使用同一套基于响应的投影。仓库内的
`number` 转为整数，不使用全局 `id` 代替；缺失或非法值保持 null。`state`
统一为大写，其中 `OPENED` 转为 `OPEN`。`url` 依次采用响应中的 `html_url`、
`web_url` 或已经是网页地址的 `url`，不把 API 地址作为标准网页地址。
`createdAt`、`updatedAt` 同时接受响应中的下划线命名。

PR 创建响应可用 `source_branch` / `target_branch` 补齐分支名及最小 `head` /
`base` 对象，不凭空生成仓库对象或提交 SHA。已有的嵌套响应字段保持不变。
优先使用布尔 `draft`；`work_in_progress` 只接受布尔或整数 0/1，不把字符串
按真假值转换。缺少 `body` 时可采用响应中的 `description`。

原始别名与标准字段一起保留。投影不从 CLI 请求参数推断服务端是否保存了
state、draft、分支或 milestone。普通人类可读输出和 dry-run 请求体不使用
这套投影。

## 创建后的读回与部分成功

成功创建的响应缺少用户请求的受支持 JSON 字段时，最多用服务端返回的正整数
编号 GET 一次。未知自定义字段不触发 GET。`--jq` 可访问完整对象，所以使用
已公布的创建字段判断是否需要读回，不尝试解析 jq 表达式。PR adapter 因设置
milestone 已做过的读回复用，不再额外 GET。

GET 响应是最终输出快照。仍缺失或 null 的字段不会被请求参数替换，也不会再次
GET。如果 GET 失败、返回非法 JSON、不是对象或编号不一致，CLI 会报告创建响应
中的编号和输出无法确认，并提示重试前先检查对象；绝不自动重复创建或回滚。
缺少可信编号时，不通过标题搜索或猜测“最新对象”来弥补。

## 仓库路径

`repo list/view --json nameWithOwner` 使用真实仓库/命名空间路径，不是简单去掉
显示名中的空白。优先 `path_with_namespace`，其次 namespace/owner path 加仓库
path，最后采用合法 `full_name`。显示字段 `name` 不变；没有充分路径证据时返回
null。

离线测试验证序列化和投影，不代表真实 GitCode 权限、仓库策略或部署验收。
