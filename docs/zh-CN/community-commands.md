# 组织与仓库讨论

`gc org list`（别名 `ls`）每行输出一个当前认证用户所属组织的登录名，无需进入仓库目录。默认最多 30 个，可用 `-L` 调整。

```sh
gc org list -L 50
gc discussion ls -R OWNER/REPO --search "构建" --state open --json number,title
gc discussion view 8 -R OWNER/REPO --comments --limit 10
gc discussion view 8 -R OWNER/REPO --comments --json comments
gc discussion replies 8 COMMENT_ID -R OWNER/REPO --page 1 --per-page 20 --json id,author,body
gc discussion create -R OWNER/REPO -c General -t "版本计划" -F roadmap.md
gc discussion edit 8 -R OWNER/REPO -c General -t "更新版本计划" -F roadmap.md
gc discussion comment 8 -R OWNER/REPO -b "计划在哪个版本交付？"
```

只操作仓库讨论，不会改动组织社区讨论。查看、修改、评论都使用正整数讨论编号；在根命令或子命令传入 `-R`，或使用当前 GitCode 仓库。创建和修改必须明确给出实际分类名称、标题和正文（`-b` 传文本，`-F` 读文件，`-F -` 读标准输入）。GitCode 的更新接口要求三个字段齐全，不会为部分更新自动读回、合并或覆盖其他字段。评论前会读取目标讨论的 ID，随后提交一条顶层评论。核对服务端返回的字段和标识后才报告成功。写操作只发送一次；如果结果不确定，应先查看服务端状态。

列表默认仅显示未关闭的讨论，按最后更新时间倒序。GitCode 不支持服务端按更新时间排序，gc 会取完所有页再排序和截取；如只关心创建时间，可用 `--sort created` 按匹配数量提前停止。分页响应异常、重复或达到 100 页仍无法确定结果完整时，会报错而不是显示不完整的排序结果。作者登录名和分类名称精确匹配；`view --comments` 只显示顶层评论，默认最新在前。

用 `view --comments --json comments` 获取顶层评论 ID。`discussion replies NUMBER COMMENT_ID` 会先在指定仓库、指定讨论的顶层评论列表中按 ID 精确匹配父评论，按创建时间升序最多读取 10 页、每页 100 条。如果找不到父评论、父评论已隐藏或删除，或在上限内无法确认，命令以非零状态退出，不请求回复，也不切换讨论、仓库或账号。

验证后只读取一页回复，保留服务端顺序。`--page`（从 1 开始）与 `--per-page`（默认 20，范围 1–100）**只控制回复分页**。已确认父评论但所选回复页为空时，JSON 输出为 `[]`。官方回复行不回显父评论 ID；两次读取不构成固定快照。JSON 字段为 `id`、`author`（登录名）、`body`（Markdown）、`createdAt`、`hidden`、`deleted`；隐藏或已删除的回复显示状态；选中的作者和正文字段为 `null`。JSON 转义控制字符及非 ASCII 字符，解码后仍是原始 Markdown。

目前是 gh 预览讨论命令的子集，不经 gh 代理。尚不支持讨论或评论 URL、写入标签、修改或删除评论、发送嵌套回复、游标、网页模式或未列出的格式化选项。各命令执行 `--help` 可查看实际支持的选项。参见[英文说明和官方 API 文档链接](../en/community-commands.md)。
