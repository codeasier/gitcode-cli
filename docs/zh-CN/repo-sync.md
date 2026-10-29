# 仓库同步前置核验

`gc repo sync OWNER/REPO` 先读取所选仓库；明确不是 fork 时，在同步请求前返回
**not a fork**，不再依赖服务端含糊的 `Project not found:null`。信息缺失或类型
含糊时返回 **cannot verify**，不把字符串、浮点数或任意整数当成可同步依据。

[官方仓库详情文档](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/)
（2026-10-29 核对）的 `fork` schema 为 integer，具体示例为 boolean。因此仅接受
布尔值或严格整数 0/1。确认是 fork 后保留原来的单次同步请求，不增加重试、强制、
source 或 branch 语义。

单测与严格 `.invalid` HTTP 契约使用合成凭据，覆盖非 fork、未知信息、读取失败及
正常前置路径；不是 live 同步验收。另行获授权后，在一次性仓库验证非 fork 无同步
写入、已知 fork 正常继续、元数据不可用时不写入。上游选择、服务端并发和完成语义
仍由现有同步 API 定义。
