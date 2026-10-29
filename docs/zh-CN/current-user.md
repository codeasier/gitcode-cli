# 当前账号别名

以下选项中的独立值 `@me` 通过 `GET /user` 解析为当前认证账号的 **login**，不会使用显示名称或猜测的 `username`：

- `gc pr list --author @me`、`--assignee @me`；
- `gc issue list --author @me`、`--assignee @me`；
- `gc issue create --assignee @me`；
- `gc issue edit --add-assignee @me`、`--remove-assignee @me`。

同一操作中的多个别名共用一次当前用户查询。普通 login 原样传递，不额外查询用户；本修复不增加 Issue 人员选项的重复/逗号列表语义，也不改变已有指派规则。PR create/edit 保持独立的[角色感知人员操作](pr-people.md)。

查询不可用、请求失败、缺失或异常 login、只有显示名称时，在 Issue/PR 请求前失败；不会发送字面量 `@me`、静默丢弃过滤条件、以显示名称代替账号或重试写入。PR list 的 `--limit 0` 仍然不发出请求。

单元回归和严格 `.invalid` HTTP 合同使用合成凭据，覆盖查询顺序、序列化值、普通 login、零条限制及写入前失败。这些是离线覆盖，不代表线上权限验收；必须通过 CLI CI，另行授权的隔离沙盒可核验账号与令牌所有者一致。
