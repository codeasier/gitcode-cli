# Tasks

- [x] Task 1: 创建 git worktree 和修复分支
  - [x] 1.1 在 `/Users/codeasier/Projects/gitcode-cli` 的父目录创建 git worktree，路径为 `/Users/codeasier/Projects/gitcode-cli-fix-unicode`
  - [x] 1.2 在 worktree 中从 main 创建分支 `fix/issue-14-windows-unicode-encode`

- [x] Task 2: 在 `utils.py` 中新增 `safe_echo()` 函数
  - [x] 2.1 实现 `safe_echo(message, err=False)` 函数，封装 `click.echo()`，对 Unicode 编码错误使用 `errors='replace'` 策略
  - [x] 2.2 添加 `safe_echo` 的单元测试（正常文本、emoji 文本、GBK 不可编码字符）

- [x] Task 3: 在 `cli.py` 入口添加 stdout/stderr 编码重配置
  - [x] 3.1 在 `main()` 函数开头添加 `_configure_stdout_encoding()` 调用，尝试 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`
  - [x] 3.2 同样处理 `sys.stderr`
  - [x] 3.3 使用 try/except 包裹，确保 reconfigure 失败时不影响程序启动

- [x] Task 4: 替换所有 `click.echo()` 为 `safe_echo()`
  - [x] 4.1 替换 `commands/issue.py` 中的所有 `click.echo` 调用
  - [x] 4.2 替换 `commands/pr.py` 中的所有 `click.echo` 调用
  - [x] 4.3 替换 `commands/auth.py` 中的所有 `click.echo` 调用
  - [x] 4.4 替换 `formatters.py` 中的所有 `click.echo` 调用
  - [x] 4.5 替换 `cli.py` 中的 `click.echo` 调用

- [x] Task 5: 添加 Unicode 编码安全相关测试
  - [x] 5.1 在 `test_utils.py` 中添加 `safe_echo` 测试
  - [x] 5.2 在 `test_formatters.py` 中添加包含 emoji 的格式化输出测试
  - [x] 5.3 在 `test_cli.py` 中添加入口编码配置测试

- [x] Task 6: 运行完整测试套件验证
  - [x] 6.1 运行 `python -m pytest tests/unit/` 确保所有测试通过
  - [x] 6.2 运行 `python -m ruff check src/ tests/` 确保 lint 通过
  - [x] 6.3 运行 `python -m ruff format --check src/ tests/` 确保格式通过
  - [x] 6.4 运行 `python -m basedpyright src/` 确保类型检查通过
  - [x] 6.5 确保测试覆盖率 >= 90%

- [x] Task 7: 提交代码并创建 PR
  - [x] 7.1 在 worktree 中 commit 所有修改
  - [x] 7.2 push 分支到 origin
  - [x] 7.3 使用 `gh pr create` 创建 PR，body 使用项目 PR 模板，关联 `Fixes #14`

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 2]
- [Task 5] depends on [Task 2, Task 3, Task 4]
- [Task 6] depends on [Task 5]
- [Task 7] depends on [Task 6]
