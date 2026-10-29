# 尚无已验证契约的写入选项

`gc` 当前对两个已识别选项明确拒绝，而不是发送不确定的字段后报告成功：

- `gc issue close --reason ...`：[官方 Issue 更新 body](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number/) 未列出关闭原因字段，发送 `state_reason` 不代表平台会保存它。
- `gc pr edit --remove-milestone`：[官方 PR 更新 body](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-number/) 只有整数 `milestone_number`，没有已验证的清空约定；不猜测 `0`、`null` 或空字符串。

命令层和直接调用的 adapter 均在请求前拒绝。与评论、重复 Issue 提示、标题、标签、人员或其他里程碑选项组合也不会执行部分修改。选项仍显示在帮助中，兼容注册表标注为当前不支持。

这是当前 CLI 的验证缺口，不断言平台永远不可能支持。确认可靠契约和验收证据后可恢复实现。省略 `--reason` 可按原逻辑关闭、评论或幂等处理；省略 `--remove-milestone` 可修改其他 PR 字段。设置正整数里程碑或按标题解析、人员、标签与 `@me` 行为保持不变；Issue 里程碑移除不在本次范围。

离线定义覆盖零请求拒绝、直接 adapter 安全、帮助/注册表锁步及正常操作。严格 `.invalid` 路由使用合成凭据，不等同线上验收。官方文档于 2026-10-29 核对；本修复不需要线上写入或更改凭据。
