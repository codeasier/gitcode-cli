# 本地 GitCode 多账号

默认的 `gc auth login` 保留旧版单 token 离线登录。需要切换 gitcode.com 账号时：

```console
gc auth login --account
gc auth login --account
gc auth status
gc auth switch --user alice
gc auth status --active --json hosts
gc auth logout --user bob
```

两次登录分别在隐藏输入框输入各自账号的个人访问令牌。脚本可通过 `--with-token` 从标准输入读取，不要把令牌写在命令行、示例文件或日志里。具名登录使用本次输入的令牌访问 `GET /user`，仅采用响应中的 login；核验失败不保存。再次登录同名账号只替换该账号的本地令牌。

- 全局 `--token` 优先于 `GC_TOKEN`，二者都优先于本地选中的账号。临时覆盖不自动落盘；登录只保存明确输入的值。有覆盖时，status 只报告实际生效的凭据；如需 switch、logout 或 `auth token --user`，请先取消覆盖。
- 文本 status 仅显示本地状态，不显示令牌或前缀，不代表远端核验通过。JSON 按列出的账号核验，核验失败记录在结果中（退出码 0），不输出原始接口错误。`--active` 仅查看生效账号。只有显式调用 `auth token` 才输出凭据；`--user LOGIN` 要求已保存的精确账号名，请勿在日志中使用。
- logout 只移除本地凭据，不撤销服务端 PAT。删除生效账号后，即使仅剩一个账号也不自动切换，需再次执行 switch。切换与登出不访问网络。
- 旧版单 token 配置可直接读取。首次具名登录会保留原 token 为 `@legacy`：`auth switch --legacy` 可显式切回，`auth logout --user @legacy` 可移除。普通 login 只替换这个未命名槽位并选中它；不要用旧版客户端对多账号配置执行登录或登出。
- 凭据仍以本地私有文件存储，不使用系统钥匙串。更新以原子替换方式写入（POSIX 目录 0700、文件 0600；Windows 使用用户目录 ACL）。并发写入会被拒绝；进程被强制终止后，只有确认没有其他认证写入任务时，才移除空的 `~/.config/gc/.auth-update.lock` 目录。

**OAuth 边界：**GitCode [文档中的授权码交换](https://docs.gitcode.com/docs/apis/oauth/) 要求已注册应用的 client secret；[MCP 服务端](../gitcode/oauth.md) 是单独的机密客户端。CLI 不内置该密钥、不假设支持公共客户端 PKCE 或设备码；未实现 `gc auth login --web`。
