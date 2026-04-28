# Tasks

- [x] Task 1: 创建独立 git worktree 并切换到修复分支
  - [x] 1.1 在项目根目录创建 git worktree，路径为 `../gitcode-cli-fix-13`
  - [x] 1.2 从 main 分支创建 `fix/pr-create-keyerror-html-url` 分支

- [x] Task 2: 修复 pr.py 中 default_formatter 的不安全字典访问
  - [x] 2.1 将 `default_formatter=lambda data: click.echo(data["html_url"])` 改为防御性访问逻辑
  - [x] 2.2 回退优先级: `html_url` → `url` → `Created PR #{number}` → `Created pull request`

- [x] Task 3: 新增测试用例覆盖 html_url 缺失场景
  - [x] 3.1 测试: API 响应缺少 html_url 但包含 url 时不崩溃
  - [x] 3.2 测试: API 响应缺少 html_url 和 url 但包含 number 时不崩溃
  - [x] 3.3 测试: API 响应包含 html_url 时行为不变

- [x] Task 4: 运行完整质量检查
  - [x] 4.1 运行 `python -m pytest tests/unit/` 确保所有测试通过
  - [x] 4.2 运行 `python -m ruff check src/ tests/` 确保 lint 通过
  - [x] 4.3 运行 `python -m ruff format --check src/ tests/` 确保格式通过
  - [x] 4.4 运行 `python -m basedpyright src/` 确保类型检查通过

- [x] Task 5: 提交代码并创建 PR
  - [x] 5.1 使用 conventional commit 格式提交: `fix: prevent KeyError when pr create response lacks html_url`
  - [x] 5.2 推送分支到 origin
  - [x] 5.3 使用 `gh pr create` 创建 PR，使用项目 PR 模板，关联 Issue #13

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 4]
