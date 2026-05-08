# 使用 Agent 操作本项目

## 你可以让 Agent 帮你做什么

你可以让 agent 协助你：

- 从 PyPI 安装 `pygitcode`
- 从当前仓库源码安装可编辑版本
- 使用 `gc auth login`、`GC_TOKEN` 或 `--token` 完成 GitCode 认证
- 运行常见的 Issue 和 Pull Request 命令
- 排查 token、仓库识别、命令调用方式等常见问题
- 在升级前先阅读变更说明，再协助完成升级与验证

## 一开始就告诉 Agent 的信息

开始前，建议明确告诉 agent：

- 你的操作系统和 shell
- 你想使用 PyPI 发布版，还是当前仓库源码版
- 是否允许它安装依赖、修改本地配置、运行联网命令、打开浏览器
- 是否必须避免打印或暴露 token
- 你当前是否在 Windows PowerShell 中，如果是，优先使用 `gitcode`
- 你要操作当前 Git 仓库，还是显式指定 `OWNER/REPO`

## 推荐提示词模板

### 安装 / 首次初始化

```text
请帮我在这台机器上安装 pygitcode。先阅读 README.zh-CN.md 和 docs/zh-CN/USING_WITH_AGENT.md，再检查是否具备 Python 3.9+ 和 pip。优先采用仓库文档里已有的安装方式；在安装软件包或写入认证配置前，先告诉我你准备执行什么。
```

### 启动 / 开始使用

```text
请帮我开始使用这个 GitCode CLI。先阅读 README.zh-CN.md 和 docs/zh-CN/USING_WITH_AGENT.md，再判断当前 shell 应该用 gc 还是 gitcode。然后安全地协助我完成认证，确认命令会作用于哪个仓库，并带我跑一个 issue 命令和一个 pr 命令。
```

### 升级 / 更新

```text
请帮我安全升级 pygitcode。先阅读 CHANGELOG.md、README.zh-CN.md 和 docs/zh-CN/USING_WITH_AGENT.md，不要直接执行破坏性操作。先告诉我当前安装版本、建议的升级路径，再执行升级并验证 CLI 还能正常工作。
```

### 故障排查

```text
请帮我排查为什么 pygitcode 不能正常工作。先阅读 README.zh-CN.md、docs/zh-CN/USING_WITH_AGENT.md 和 CHANGELOG.md，然后依次检查安装状态、Python 版本、当前 shell 应该用 gc 还是 gitcode、token 配置、仓库识别，以及我执行失败的具体命令。
```

## Agent 应先读取哪些文件

建议让 agent 优先读取：

- `README.zh-CN.md`
- `docs/zh-CN/USING_WITH_AGENT.md`
- `CHANGELOG.md`
- `docs/zh-CN/index.md`
- `docs/zh-CN/gh-compatibility.md`
- 如果你是从源码安装而不是直接使用 PyPI 包，再读 `docs/zh-CN/development.md`

## 安装 / 配置流程

仓库里已经写明了发布版安装命令：

```bash
pip install pygitcode
```

安装后会同时提供 `gc` 和 `gitcode` 两个命令。

如果从源码安装，仓库文档中的步骤是：

```bash
git clone https://github.com/codeasier/gitcode-cli.git
cd gitcode-cli
pip install -e ".[dev]"
```

通常可以让 agent 按这个顺序协助你：

1. 检查 Python 和 pip 是否可用
2. 确认你想安装 PyPI 发布版还是源码版
3. 执行安装
4. 判断当前 shell 应该使用 `gc` 还是 `gitcode`
5. 协助配置认证
6. 运行一个最小验证命令，例如 `gc version` 或 `gitcode version`

## 认证流程

这个项目按以下优先级读取 token：

1. `--token`
2. `GC_TOKEN`
3. `~/.config/gc/config.json`

仓库文档中已经列出的认证命令：

```bash
gc auth login
gc auth status
gc auth token
gc auth logout
```

agent 在以下动作前应先征求你确认：

- 写入 `~/.config/gc/config.json`
- 在终端打印 token
- 把 token 保存到文档约定路径之外的位置

如果你更偏好非交互方式，应明确告诉 agent 是否允许使用 `GC_TOKEN`，或使用 `gc auth login --with-token` 从标准输入读取 token。

## 首次运行 / 基本使用

README 中已经给出了这些基础命令：

```bash
gc issue list
gc issue view 42
gc pr list
gc pr create --fill
gc pr merge 42 --squash
```

也支持显式指定仓库：

```bash
gc issue list -R owner/repo
gc pr list -R owner/repo
```

可以让 agent 按这个顺序协助你：

1. 先确认认证是否可用
2. 先确认当前目录是否为 Git 仓库
3. 判断应直接使用当前仓库，还是显式传入 `-R owner/repo`
4. 先跑一个只读、安全的命令，例如 `gc issue list` 或 `gc pr list`
5. 只有在你明确要求后，再继续创建、评论、关闭、合并或评审等写操作

## 更新 / 升级流程

仓库提供了 `CHANGELOG.md`，并声明遵循语义化版本。升级前，agent 应先：

1. 阅读 `CHANGELOG.md`
2. 用 `gc version` 或 `gitcode version` 确认当前版本
3. 判断你当前是通过 PyPI 安装，还是通过源码可编辑安装
4. 根据安装方式给出准确的升级命令
5. 升级后再验证认证状态和一个基础 CLI 命令

如果你直接使用当前仓库源码环境，修改可编辑安装前应先让 agent 阅读 `docs/zh-CN/development.md`。

## 故障排查流程

当安装或使用失败时，可以让 agent 按以下顺序检查：

1. Python 版本是否满足 `>=3.9`
2. `pygitcode` 是否已正确安装
3. 当前 shell 应该使用 `gc` 还是 `gitcode`
4. 是否通过 `--token`、`GC_TOKEN` 或 `~/.config/gc/config.json` 提供了认证
5. 当前目录是否是带有可用 `origin` 远端的 Git 仓库
6. 当前命令是否应该显式使用 `-R owner/repo`
7. 失败命令是否属于“已识别但尚未实现”的 `gh` 兼容能力

仓库中可直接确认的几个事实：

- `gc` 尽量对齐 `gh` 的命令习惯，但仍存在兼容性差异
- 在 Windows PowerShell 中，建议优先使用 `gitcode`，因为 `gc` 会与 `Get-Content` 冲突
- 部分不支持的 `gh` 风格参数会直接报错，而不是静默推断行为

## 需要先确认的动作

agent 不应默认直接执行以下动作，应先征求你确认：

- 安装或升级软件包
- 写入认证配置
- 打印、导出或持久化 token
- 打开浏览器或访问 Web 页面
- 创建、编辑、关闭、合并、重开 Issue 或 Pull Request
- 在 `pr merge --delete-branch` 中删除远端分支
- 对当前仓库之外的其他仓库执行命令

## 备注

- PyPI 发布包名是 `pygitcode`。
- CLI 同时提供 `gc` 和 `gitcode`。
- `gc auth login` 默认会交互式提示输入 token；如果需要非交互方式，可结合 `--with-token` 使用。
- 如果当前仓库识别不稳定，可以明确要求 agent 优先使用 `-R owner/repo`。
- 如果你需要确认 `gh` 兼容边界，先让 agent 读取 `docs/zh-CN/gh-compatibility.md`。
