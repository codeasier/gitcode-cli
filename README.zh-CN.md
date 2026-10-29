# pygitcode

> `pygitcode` 是面向 [GitCode](https://gitcode.com/)（`api.gitcode.com`）的命令行工具，命令体验尽量对齐 GitHub CLI（`gh`）。

[![PyPI](https://img.shields.io/pypi/v/pygitcode)](https://pypi.org/project/pygitcode/)
[![Python](https://img.shields.io/pypi/pyversions/pygitcode)](https://pypi.org/project/pygitcode/)
[![License](https://img.shields.io/pypi/l/pygitcode)](https://github.com/codeasier/gitcode-cli/blob/main/LICENSE)

[English](README.md) | 中文

如果你正在借助 agent 安装、使用、升级或排障，请先阅读 [docs/zh-CN/USING_WITH_AGENT.md](docs/zh-CN/USING_WITH_AGENT.md)。

## 安装

```bash
pip install pygitcode
```

安装后会提供 `gc` 和 `gitcode` 两个命令。

如果希望原有 `gh` 命令能按仓库自动路由到 GitCode 或 GitHub，可以安装并配置可选代理：

```bash
gc setup gh-proxy --configure
```

该命令会安装 shim、在 shell 中加入受管 `PATH` 配置块，并注册 OpenCode 指令，让 agent 在回退 API 前先尝试 dispatcher；完成后需重启 OpenCode。代理会将 GitCode 仓库转给 `gc`，将 GitHub 或无法判断的场景转给原生 `gh`；当目标为 GitCode 时，不支持的命令会直接报错。路由控制和卸载方式见[兼容性说明](docs/zh-CN/gh-compatibility.md#可选-gh-代理)。

## 快速开始

如果你熟悉 GitHub CLI（`gh`），可以直接从这些常见流程开始：

```bash
gc auth login
gc issue list
gc issue view 42
gc pr list
gc pr create --fill
gc pr audit
gc pr merge 42 --squash
gc repo view owner/repo
gc repo clone owner/repo
```

在 Windows PowerShell 中请优先使用 `gitcode`，因为 `gc` 是内置 `Get-Content` 别名。

`gc pr audit` 会为每条未通过的 R1-R4 合并就绪规则打印原因。列表模式下，除 HTTP 401 以外的错误会记在对应 PR 上，默认退出码为 0（加 `--fail-exit` 则为 1）。HTTP 401 会中止剩余列表并退出 1，与 `--fail-exit` 无关。

## GitCode MCP

本仓库同时维护独立安装的 [`codeasier-gitcode-mcp`](packages/gitcode-mcp) 运行时（Python 3.11+），提供 stdio、Streamable HTTP、OAuth 和 31 个 GitCode 工具。CLI 与 MCP 是两个独立分发包：安装 `pygitcode` 不会引入 MCP、ASGI 或加密依赖。请参阅 [MCP 文档](docs/gitcode/README.md)和[迁移指南](docs/gitcode/migration.md)；Codex 专属插件桥接仍由 [codex-codeasier](https://github.com/codeasier/codex-codeasier/tree/main/plugins/gitcode) 维护。

## 文档

- [文档索引](docs/zh-CN/index.md)
- [开发指南](docs/zh-CN/development.md)
- [兼容性说明](docs/zh-CN/gh-compatibility.md)

## 仓库选择

默认情况下，命令会使用当前 Git 仓库。也可以通过 `-R owner/repo` 显式指定仓库：

```bash
gc issue list -R owner/repo
gc pr list -R owner/repo
```

## 认证

`gc` 按以下优先级读取 token：

1. `--token` 参数
2. `GC_TOKEN` 环境变量
3. `gc auth login` 写入的 `~/.config/gc/config.json`

常用命令：

```bash
gc auth login
gc auth status
gc auth token
gc auth logout
```

## License

MIT
