# 同步 fork 的一个分支

`gc repo sync OWNER/FORK --branch release/1` 请求 GitCode 从父仓库同步 fork 的
`release/1` 分支。省略 `--branch` 时，gc 读取**父仓库而非 fork 的默认分支**；
父仓库或默认分支不明确时，需要显式指定 `--branch`。[GitCode 官方说明](https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-sync-repo/)指出不传分支会更新所有分支，因此 CLI 从不发送缺少分支的同步请求。

同步写入前，gc 读取目标的[仓库详情](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/)。
`fork` 字段仅接受布尔值或严格整数 0/1；非 fork 或信息含糊都不发起同步。
gc 仅发起一次同步，只有收到布尔值 `repo_sync_result=true` 才报告成功。
结果不确定时，应先在远端核验，不直接重试。

该能力仅为 GitCode 的远端 fork 同步，不会更新本地检出；不支持任意指定源仓、
强制重置，也不保证分支已有分歧时与 GitHub 行为完全一致。
离线合成契约验证了分支参数与请求行为，未执行真实仓库写入验收。

## 只查状态，不执行同步

`gc repo sync-status OWNER/FORK -b release/1` 通过**一次 GET**
[查询 fork 同步状态](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-sync-repo/)。
先登录，再显式传入仓库和一个短分支名，不接受 URL、`-R` 或 `refs/heads/…`。
不读取本地 origin 或默认分支，不跟随重定向、不重试，也不会回退到上述 PUT。

输出 JSON 保留服务端布尔值 `repo_sync_result` 和字符串 `repo_sync_message`。
无论布尔值是真还是假，都只是读取成功，不能据此判断提交祖先或领先、落后数。
含控制字符、超长、疑似凭据或链接的消息不展示；响应格式不符则报错且无部分输出。
该命令仅属于原生 `gc`，不通过 `gh` 或 MCP 提供。请求契约仅经离线验证，未实测真实 fork。
