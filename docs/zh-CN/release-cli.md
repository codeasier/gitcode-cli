# 发行版工作流

请直接调用 `gc`（Windows 可用 `gitcode`）；可选的 `gh` 代理不会将此命令组转给 GitCode。

下列命令支持全局或子命令的 `-R 组织/仓库` 参数：

```sh
gc release list -R org/project --limit 20 --exclude-pre-releases
gc release view v1.0 -R org/project --json tagName,name,assets
gc release download v1.0 -R org/project -p '*.whl' -D dist
gc release download -R org/project --archive zip -O source.zip
gc release create v1.0 -R org/project --verify-tag --title '1.0' --notes-file NOTES.md
gc release upload v1.0 -R org/project dist/project.whl
gc release edit v1.0 -R org/project --notes-file updated.md
gc release delete-asset v1.0 project.whl -R org/project
```

- 不传 tag 时按 GitCode 的 latest 选择器读取，而不是取列表首项或最后更新项；显式传入 `latest` 表示查询名为 latest 的标签。未指定 tag 的下载必须带 `--pattern` 或 `--archive`。
- 默认只选上传的附件，不把 GitCode 生成的源码包混入结果。源码包通过 `--archive zip|tar.gz` 单独选择。普通 ZIP 附件不是源码包。
- 附件通过独立 HTTPS 通道流式传输，不向存储域名或重定向目标传 GitCode 凭据、不复用代理配置。若服务提供长度或 SHA-256 则校验，校验后才落到最终文件名；没有摘要就不能声称已验证哈希或发布者签名。遇到未受信域名、危险或重名文件、失败的私仓临时链接均中止。多文件失败保留先前已完成的文件。
- 下载到文件与从文件上传当前只在支持无链接跟随目录描述符的 POSIX 平台启用。请使用可信且无符号链接的路径；下载目录不能由未授权用户写入。其他平台可使用元数据命令以及重定向 `download --output -`。
- 不覆盖已有文件；下载添加 `--clobber` 才覆盖，`--skip-existing` 跳过而不复核已有文件。单文件可使用 `-O -` 输出到重定向的标准输出，不允许直接输出到终端。
- `create` 直接发布。若 tag 不存在，API 可能从指定 `--target` 或默认分支创建标签；`--verify-tag` 在提交前检查同名 tag，但不是服务端原子条件。创建时指定附件，先发布再上传，部分失败不自动回滚。
- 创建或删除远端资源前会先为全部上传输入制作私有文件快照，拒绝符号链接和大小写或 Unicode 规范化后重名的文件。需要预留足够临时空间。上传申请临时签名后 PUT，随后读取发行版核验附件注册，比较服务返回的大小和摘要。上传同名文件默认拒绝；显式 `upload --clobber` 先删除对应附件再上传，失败可能丢失旧附件，核对远端后再重试。
- 创建、编辑仅在响应或一次回读确认请求的标题、说明和显式状态后报告成功。不确定的写操作应先核对远端，不要盲目重试。编辑会先读取并保留未指定的必填标题/说明。GitCode 未公开编辑的并发前置条件。预发布与最新状态互斥。单个发行版网页链接缺失时，JSON 不虚构链接，`view --web` 会提示并打开仓库发行版列表。
- 公开 API 可按附件 ID 删除单个附件，没有独立的删除发行版接口，不能用删除 tag 代替。草稿、证书验证、生成发行说明、讨论区等也不等同于 GitHub 能力。

[完整接口列表与官方来源](../en/release-cli.md)

## 不重新下载，比对已有文件

`gc release check-digest TAG PATH -R OWNER/REPO` 将本地文件与 GitCode 附件元数据中的 SHA-256 比对，**不是发布者签名或认证**，也不等价于 `gh release verify` / `verify-asset`。显式指定仓库和精确标签，本地文件名须与唯一上传附件名完全一致；支持 POSIX 下受信任、非符号链接的普通文件，最大 1 GiB。只查询一次[按标签获取发行版](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-releases-tags-tag/)，不请求下载地址，不传送本地文件或文件名，不写盘。

[GitCode 的按标签查询定义](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-releases-tags-tag/)将 `digest`（SHA-256）列为可选字段；[AtomGit 同端点的字段表](https://atomgit-api-doc.atomgit.com/14.release/222.get_repository_release_by_tag_name.html)没有列出摘要，响应示例也未返回 `type`。不能假定每个附件都有类型和摘要。此命令要求正整数 ID 和 GitCode 提供的 SHA-256，并接受 `ATTACH_FILE`；对 GitCode 返回的 `attach`，只在元数据中的地址与所选仓库、标签和文件名对应的 GitCode 下载路径完全匹配时接受。命令只比对地址，不会访问它。如果提供大小，也须一致。元数据缺失、源码归档、重名或不匹配均以非零退出。成功只描述本次比对，不代表标签或附件不可变。

`gc release view --json zipballUrl,tarballUrl` 只投影 GitCode 已返回的源码归档链接；缺失、歧义或不能确认属于同一仓库和标签的 URL 返回 `null`。不下载、不改变附件语义、不猜测链接。
