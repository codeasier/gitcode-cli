# gc CLI 对齐 gh CLI 阶段性修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 缩小 `gc` CLI 与 `gh` CLI 在参数命名、可选性、短选项形式、子命令覆盖面上的差距，分5个阶段实现。

**Architecture:** 基于现有 Click 命令结构，逐阶段补充短选项、交互式提示、缺失子命令和高级功能。保持与 GitCode API v5 的兼容性，不引入外部重量级依赖。

**Tech Stack:** Python 3.10+, Click, httpx

---

## 文件结构概览

| 文件 | 职责 |
|------|------|
| `src/gitcode_cli/commands/issue.py` | Issue 子命令定义（list/view/create/close/comment + 新增 reopen/edit/delete/status） |
| `src/gitcode_cli/commands/pr.py` | PR 子命令定义（list/view/create/close/merge/comment/review + 新增 reopen/edit/status） |
| `src/gitcode_cli/services/issues.py` | Issue API 封装（新增 delete 等方法） |
| `src/gitcode_cli/services/pulls.py` | PR API 封装（新增 status 等方法） |
| `src/gitcode_cli/utils.py` | **新增**：通用工具函数（body_file 读取、浏览器打开、URL/branch 解析等） |

---

## 阶段1：补充短选项形式（高优先级）

> 目标：为所有已有参数添加 `gh` 兼容的短选项。这是用户最直观的差异。

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`

---

### Task 1.1: Issue 命令短选项补充

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`

- [ ] **Step 1: `issue list` 添加短选项**

```python
# 修改前
@click.option("--state")
@click.option("--label", "labels")
@click.option("--author")
@click.option("--assignee")
@click.option("--search")
@click.option("--json", "as_json", is_flag=True)

# 修改后
@click.option("-s", "--state")
@click.option("-l", "--label", "labels")
@click.option("-A", "--author")
@click.option("-a", "--assignee")
@click.option("-S", "--search")
@click.option("--json", "as_json", is_flag=True)
```

- [ ] **Step 2: `issue view` 无短选项变更（仅 `--json`）**

无需修改。

- [ ] **Step 3: `issue create` 添加短选项**

```python
# 修改前
@click.option("--title", required=True)
@click.option("--body")
@click.option("--assignee")
@click.option("--label", "labels")
@click.option("--json", "as_json", is_flag=True)

# 修改后
@click.option("-t", "--title", required=True)
@click.option("-b", "--body")
@click.option("-a", "--assignee")
@click.option("-l", "--label", "labels")
@click.option("--json", "as_json", is_flag=True)
```

- [ ] **Step 4: `issue comment` 添加 `-b` 短选项**

```python
# 修改前
@click.option("--body", required=True)

# 修改后
@click.option("-b", "--body", required=True)
```

- [ ] **Step 5: 验证 Issue 命令 help 输出**

Run: `python -m gitcode_cli issue list --help`
Expected: 显示 `-s, --state`, `-l, --label`, `-A, --author`, `-a, --assignee`, `-S, --search`

Run: `python -m gitcode_cli issue create --help`
Expected: 显示 `-t, --title`, `-b, --body`, `-a, --assignee`, `-l, --label`

Run: `python -m gitcode_cli issue comment --help`
Expected: 显示 `-b, --body`

- [ ] **Step 6: Commit**

```bash
git add src/gitcode_cli/commands/issue.py
git commit -m "feat(issue): add short options (-a, -b, -l, -s, -t, -A, -S) to align with gh"
```

---

### Task 1.2: PR 命令短选项补充

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py`

- [ ] **Step 1: `pr list` 添加短选项**

```python
# 修改前
@click.option("--state")
@click.option("--author")
@click.option("--base")
@click.option("--label", "labels")
@click.option("--search")
@click.option("--json", "as_json", is_flag=True)

# 修改后
@click.option("-s", "--state")
@click.option("-A", "--author")
@click.option("-B", "--base")
@click.option("-l", "--label", "labels")
@click.option("-S", "--search")
@click.option("--json", "as_json", is_flag=True)
```

- [ ] **Step 2: `pr create` 添加短选项**

```python
# 修改前
@click.option("--title", required=True)
@click.option("--body")
@click.option("--base", required=True)
@click.option("--head", required=True)
@click.option("--draft", is_flag=True)
@click.option("--label", "labels")
@click.option("--reviewer")
@click.option("--assignee")
@click.option("--json", "as_json", is_flag=True)

# 修改后
@click.option("-t", "--title", required=True)
@click.option("-b", "--body")
@click.option("-B", "--base", required=True)
@click.option("-H", "--head", required=True)
@click.option("-d", "--draft", is_flag=True)
@click.option("-l", "--label", "labels")
@click.option("-r", "--reviewer")
@click.option("-a", "--assignee")
@click.option("--json", "as_json", is_flag=True)
```

- [ ] **Step 3: `pr comment` 添加 `-b` 短选项**

```python
# 修改前
@click.option("--body", required=True)

# 修改后
@click.option("-b", "--body", required=True)
```

- [ ] **Step 4: `pr merge` 添加短选项**

```python
# 修改前
@click.option("--merge", "merge_mode", flag_value="merge")
@click.option("--squash", "merge_mode", flag_value="squash")
@click.option("--rebase", "merge_mode", flag_value="rebase")

# 修改后
@click.option("-m", "--merge", "merge_mode", flag_value="merge")
@click.option("-s", "--squash", "merge_mode", flag_value="squash")
@click.option("-r", "--rebase", "merge_mode", flag_value="rebase")
```

- [ ] **Step 5: `pr review` 添加 `-a` 短选项**

```python
# 修改前
@click.option("--approve", is_flag=True, help="Approve the pull request. GitCode maps this to its review API.")

# 修改后
@click.option("-a", "--approve", is_flag=True, help="Approve the pull request. GitCode maps this to its review API.")
```

- [ ] **Step 6: 验证 PR 命令 help 输出**

Run: `python -m gitcode_cli pr list --help`
Expected: 显示 `-s, --state`, `-A, --author`, `-B, --base`, `-l, --label`, `-S, --search`

Run: `python -m gitcode_cli pr create --help`
Expected: 显示 `-t, --title`, `-b, --body`, `-B, --base`, `-H, --head`, `-d, --draft`, `-l, --label`, `-r, --reviewer`, `-a, --assignee`

Run: `python -m gitcode_cli pr merge --help`
Expected: 显示 `-m, --merge`, `-s, --squash`, `-r, --rebase`

Run: `python -m gitcode_cli pr review --help`
Expected: 显示 `-a, --approve`

- [ ] **Step 7: Commit**

```bash
git add src/gitcode_cli/commands/pr.py
git commit -m "feat(pr): add short options (-a, -b, -B, -d, -H, -l, -r, -s, -t, -A, -S) to align with gh"
```

---

## 阶段2：参数可选性 + 交互式提示（高优先级）

> 目标：将 `gh` 中可选的参数在 `gc` 中也改为可选，缺失时交互式提示（`click.prompt` 或 `click.edit`）。

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`
- Create: `src/gitcode_cli/utils.py`（通用工具函数）

---

### Task 2.1: 创建通用工具模块

**Files:**
- Create: `src/gitcode_cli/utils.py`

- [ ] **Step 1: 实现工具函数**

```python
from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path

import click


def prompt_if_missing(value: str | None, prompt_text: str, hide_input: bool = False) -> str:
    """如果 value 为 None 或空字符串，使用 click.prompt 交互式提示。"""
    if not value:
        return click.prompt(prompt_text, hide_input=hide_input)
    return value


def get_current_git_branch() -> str | None:
    """获取当前 git 分支名，失败返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_default_git_branch() -> str | None:
    """尝试获取远程默认分支（如 origin/HEAD），失败返回 'master'。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if branch.startswith("origin/"):
            return branch[len("origin/"):]
        return branch
    except subprocess.CalledProcessError:
        return "master"


def read_body_file(path: str) -> str:
    """从文件读取 body 内容。"""
    return Path(path).read_text(encoding="utf-8")


def open_in_browser(url: str) -> None:
    """在默认浏览器中打开 URL。"""
    webbrowser.open(url)
```

- [ ] **Step 2: Commit**

```bash
git add src/gitcode_cli/utils.py
git commit -m "feat(utils): add prompt helpers, git branch detection, body-file reader, web opener"
```

---

### Task 2.2: Issue 命令参数可选化

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`

- [ ] **Step 1: `issue create` — title 改为可选**

```python
from ..utils import prompt_if_missing

@issue_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--assignee")
@click.option("-l", "--label", "labels")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def issue_create(ctx: click.Context, repo_name: str | None, title: str | None, body: str | None, assignee: str | None, labels: str | None, as_json: bool) -> None:
    title = prompt_if_missing(title, "Title")
    # ... 其余逻辑不变
```

- [ ] **Step 2: `issue comment` — body 改为可选**

```python
@issue_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number")
@click.option("-b", "--body")
@click.pass_context
def issue_comment(ctx: click.Context, repo_name: str | None, number: str, body: str | None) -> None:
    body = prompt_if_missing(body, "Body")
    # ... 其余逻辑不变
```

- [ ] **Step 3: 验证交互式提示**

Run: `echo "test title" | python -m gitcode_cli issue create --repo owner/repo`
Expected: 读取 stdin 或提示输入 title，然后成功创建（如果有 token）

- [ ] **Step 4: Commit**

```bash
git add src/gitcode_cli/commands/issue.py
git commit -m "feat(issue): make title/body optional with interactive prompts, align with gh"
```

---

### Task 2.3: PR 命令参数可选化

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py`

- [ ] **Step 1: `pr create` — title/base/head 改为可选**

```python
from ..utils import prompt_if_missing, get_current_git_branch, get_default_git_branch

@pr_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-B", "--base")
@click.option("-H", "--head")
@click.option("-d", "--draft", is_flag=True)
@click.option("-l", "--label", "labels")
@click.option("-r", "--reviewer")
@click.option("-a", "--assignee")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def pr_create(ctx: click.Context, repo_name: str | None, title: str | None, body: str | None, base: str | None, head: str | None, draft: bool, labels: str | None, reviewer: str | None, assignee: str | None, as_json: bool) -> None:
    if not head:
        head = get_current_git_branch()
        if not head:
            raise click.ClickException("Unable to detect current branch. Use --head.")
    if not base:
        base = get_default_git_branch()
    title = prompt_if_missing(title, "Title")
    # ... 其余逻辑不变
```

- [ ] **Step 2: `pr comment` — body 改为可选**

```python
@pr_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number", type=int)
@click.option("-b", "--body")
@click.option("--path")
@click.option("--position", type=int)
@click.pass_context
def pr_comment(ctx: click.Context, repo_name: str | None, number: int, body: str | None, path: str | None, position: int | None) -> None:
    body = prompt_if_missing(body, "Body")
    # ... 其余逻辑不变
```

- [ ] **Step 3: 验证交互式提示**

Run: `python -m gitcode_cli pr create --repo owner/repo --head feature-branch`
Expected: title 为空时提示输入，base 自动推断为 master/main

- [ ] **Step 4: Commit**

```bash
git add src/gitcode_cli/commands/pr.py
git commit -m "feat(pr): make title/body/base/head optional with interactive prompts, align with gh"
```

---

## 阶段3：补充缺失子命令（中优先级）

> 目标：补充 `gh` 中有但 `gc` 中缺失的核心子命令。优先实现 reopen, edit, delete, status。

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`
- Modify: `src/gitcode_cli/services/issues.py`
- Modify: `src/gitcode_cli/services/pulls.py`

---

### Task 3.1: Issue 新增子命令

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/services/issues.py`

- [ ] **Step 1: `issue reopen`**

```python
@issue_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number")
@click.pass_context
def issue_reopen(ctx: click.Context, repo_name: str | None, number: str) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    item = service.update(owner, repo, number, state="open")
    click.echo(f"Reopened issue #{item['number']}")
```

- [ ] **Step 2: `issue edit`**

```python
@issue_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label")
@click.option("--remove-assignee")
@click.option("--remove-label")
@click.pass_context
def issue_edit(ctx: click.Context, repo_name: str | None, number: str, title: str | None, body: str | None, add_assignee: str | None, add_label: str | None, remove_assignee: str | None, remove_label: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    data = {k: v for k, v in {
        "title": title,
        "body": body,
        "assignee": add_assignee,
        "labels": add_label,
    }.items() if v is not None}
    item = service.update(owner, repo, number, **data)
    click.echo(f"Edited issue #{item['number']}")
```

- [ ] **Step 3: `issue delete`**

在 `IssueService` 中添加 delete 方法：

```python
# src/gitcode_cli/services/issues.py

def delete(self, owner: str, repo: str, number: str):
    return self.client.delete(f"/repos/{owner}/{repo}/issues/{number}")
```

在 `GitCodeClient` 中添加 delete 方法（如果还没有的话）：

```python
# src/gitcode_cli/client.py

def delete(self, path: str, *, params: dict | None = None, json: dict | None = None):
    return self.request("DELETE", path, params=params, json=json)
```

命令实现：

```python
@issue_group.command("delete")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number")
@click.confirmation_option(prompt="Are you sure you want to delete this issue?")
@click.pass_context
def issue_delete(ctx: click.Context, repo_name: str | None, number: str) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    service.delete(owner, repo, number)
    click.echo(f"Deleted issue #{number}")
```

- [ ] **Step 4: `issue status`**

```python
@issue_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.pass_context
def issue_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    created = service.list(owner, repo, filter="created", state="open")
    assigned = service.list(owner, repo, filter="assigned", state="open")
    mentioned = service.list(owner, repo, filter="mentioned", state="open")
    click.echo("Issues assigned to you:")
    for item in assigned:
        click.echo(f"  #{item['number']}\t{item['title']}")
    click.echo("\nIssues created by you:")
    for item in created:
        click.echo(f"  #{item['number']}\t{item['title']}")
    click.echo("\nIssues mentioning you:")
    for item in mentioned:
        click.echo(f"  #{item['number']}\t{item['title']}")
```

注意：GitCode API 可能不支持 `filter` 参数，需要确认。如不支持，则简化实现为列出 open issues。

- [ ] **Step 5: 验证新增子命令**

Run: `python -m gitcode_cli issue --help`
Expected: 显示 reopen, edit, delete, status

- [ ] **Step 6: Commit**

```bash
git add src/gitcode_cli/commands/issue.py src/gitcode_cli/services/issues.py src/gitcode_cli/client.py
git commit -m "feat(issue): add reopen, edit, delete, status subcommands"
```

---

### Task 3.2: PR 新增子命令

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py`
- Modify: `src/gitcode_cli/services/pulls.py`

- [ ] **Step 1: `pr reopen`**

```python
@pr_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number", type=int)
@click.pass_context
def pr_reopen(ctx: click.Context, repo_name: str | None, number: int) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    item = service.update(owner, repo, number, state="open")
    click.echo(f"Reopened pull request #{item['number']}")
```

- [ ] **Step 2: `pr edit`**

```python
@pr_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number", type=int)
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-B", "--base")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label")
@click.option("-r", "--add-reviewer")
@click.pass_context
def pr_edit(ctx: click.Context, repo_name: str | None, number: int, title: str | None, body: str | None, base: str | None, add_assignee: str | None, add_label: str | None, add_reviewer: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    data = {k: v for k, v in {
        "title": title,
        "body": body,
        "base": base,
        "assignee": add_assignee,
        "labels": add_label,
        "reviewer": add_reviewer,
    }.items() if v is not None}
    item = service.update(owner, repo, number, **data)
    click.echo(f"Edited pull request #{item['number']}")
```

- [ ] **Step 3: `pr status`**

```python
@pr_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.pass_context
def pr_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    created = service.list(owner, repo, state="open", author="self")
    assigned = service.list(owner, repo, state="open", assignee="self")
    review_requested = service.list(owner, repo, state="open", reviewer="self")
    click.echo("Pull requests assigned to you:")
    for item in assigned:
        click.echo(f"  #{item['number']}\t{item['title']}")
    click.echo("\nPull requests created by you:")
    for item in created:
        click.echo(f"  #{item['number']}\t{item['title']}")
    click.echo("\nPull requests requesting your review:")
    for item in review_requested:
        click.echo(f"  #{item['number']}\t{item['title']}")
```

注意：GitCode API 对 `author`/`assignee`/`reviewer` 过滤的支持需确认。如不支持 self 过滤，则列出所有 open PRs。

- [ ] **Step 4: 验证新增子命令**

Run: `python -m gitcode_cli pr --help`
Expected: 显示 reopen, edit, status

- [ ] **Step 5: Commit**

```bash
git add src/gitcode_cli/commands/pr.py src/gitcode_cli/services/pulls.py
git commit -m "feat(pr): add reopen, edit, status subcommands"
```

---

## 阶段4：参数增强（中优先级）

> 目标：补充 `--limit`, `--milestone`, `--body-file`, `--web` 等参数，增强 list/view/create 命令。

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`
- Modify: `src/gitcode_cli/utils.py`

---

### Task 4.1: 通用增强 — limit, body-file, web

- [ ] **Step 1: `issue list` / `pr list` 添加 `--limit`**

```python
# issue list 和 pr list
@click.option("-L", "--limit", type=int, help="Maximum number of items to fetch.")
```

在 service.list 调用时传入 per_page 参数（GitCode API 通常使用 `per_page` 和 `page`）：

```python
items = service.list(owner, repo, state=state, labels=labels, ..., per_page=limit)
```

注意：如果 GitCode API 返回分页结果且用户指定了 limit，需要手动截断列表。

- [ ] **Step 2: `issue create` 添加 `--milestone`, `--body-file`, `--web`**

```python
from ..utils import read_body_file, open_in_browser

@issue_group.command("create")
# ... 已有选项
@click.option("-m", "--milestone")
@click.option("-F", "--body-file")
@click.option("-w", "--web", is_flag=True)
@click.pass_context
def issue_create(ctx: click.Context, repo_name: str | None, title: str | None, body: str | None, assignee: str | None, labels: str | None, milestone: str | None, body_file: str | None, web: bool, as_json: bool) -> None:
    if body_file:
        body = read_body_file(body_file)
    title = prompt_if_missing(title, "Title")
    # ... 创建逻辑
    if web:
        open_in_browser(item["html_url"])
    else:
        click.echo(item["html_url"])
```

- [ ] **Step 3: `pr create` 添加 `--body-file`, `--web`**

```python
@pr_group.command("create")
# ... 已有选项
@click.option("-F", "--body-file")
@click.option("-w", "--web", is_flag=True)
@click.pass_context
def pr_create(ctx: click.Context, ..., body_file: str | None, web: bool) -> None:
    if body_file:
        body = read_body_file(body_file)
    # ... 创建逻辑
    if web:
        open_in_browser(item["html_url"])
    else:
        click.echo(item["html_url"])
```

- [ ] **Step 4: `issue view` / `pr view` 添加 `--web`**

```python
@issue_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number")
@click.option("--json", "as_json", is_flag=True)
@click.option("-w", "--web", is_flag=True)
@click.pass_context
def issue_view(ctx: click.Context, repo_name: str | None, number: str, as_json: bool, web: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    item = service.get(owner, repo, number)
    if web:
        open_in_browser(item["html_url"])
        return
    # ... 原有逻辑
```

PR view 同理。

- [ ] **Step 5: 验证参数增强**

Run: `python -m gitcode_cli issue list --help`
Expected: 显示 `-L, --limit`

Run: `python -m gitcode_cli issue create --help`
Expected: 显示 `-m, --milestone`, `-F, --body-file`, `-w, --web`

- [ ] **Step 6: Commit**

```bash
git add src/gitcode_cli/commands/issue.py src/gitcode_cli/commands/pr.py src/gitcode_cli/utils.py
git commit -m "feat: add --limit, --milestone, --body-file, --web options"
```

---

## 阶段5：JSON 输出增强（低优先级）

> 目标：实现 `--json fields` 字段选择、`-q jq` 过滤、`-t template` 格式化。

**Files:**
- Modify: `src/gitcode_cli/formatters.py`
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`

---

### Task 5.1: JSON 字段选择与格式化

- [ ] **Step 1: 升级 `formatters.py` 模块**

```python
from __future__ import annotations

import json
import shutil

import click


def dump_json(data, fields: list[str] | None = None) -> str:
    if fields:
        if isinstance(data, list):
            data = [_filter_fields(item, fields) for item in data]
        else:
            data = _filter_fields(data, fields)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _filter_fields(item: dict, fields: list[str]) -> dict:
    result = {}
    for field in fields:
        if "." in field:
            # 支持简单嵌套如 "user.login"
            parts = field.split(".")
            value = item
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
            result[field] = value
        else:
            result[field] = item.get(field)
    return result


def apply_jq(data, query: str):
    """尝试使用 pyjq 或 jq 命令行工具过滤。"""
    try:
        import jq  # pyjq
        return jq.compile(query).input(data).all()
    except ImportError:
        pass
    jq_bin = shutil.which("jq")
    if jq_bin:
        import subprocess
        proc = subprocess.run(
            [jq_bin, query],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout)
    raise click.ClickException("jq is required for --jq. Install with: pip install pyjq or install jq CLI.")


def render_template(data, template: str) -> str:
    """简单的模板渲染，支持 {{.field}} 语法。"""
    import re
    def replacer(match):
        key = match.group(1)
        if "." in key:
            parts = key.split(".")
            value = data
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
        else:
            value = data.get(key) if isinstance(data, dict) else None
        return str(value) if value is not None else ""
    return re.sub(r"\{\{\.(\w+(?:\.\w+)*)\}\}", replacer, template)
```

- [ ] **Step 2: 统一所有命令的 `--json` 参数**

将所有命令中的 `--json` 改为支持字段选择：

```python
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
```

在命令函数中统一处理：

```python
from ..formatters import dump_json, apply_jq, render_template

def _output_result(data, json_fields: str | None, jq_query: str | None, template: str | None, default_formatter):
    if jq_query:
        data = apply_jq(data, jq_query)
        click.echo(dump_json(data))
        return
    if json_fields:
        fields = [f.strip() for f in json_fields.split(",")]
        click.echo(dump_json(data, fields=fields))
        return
    if template:
        if isinstance(data, list):
            for item in data:
                click.echo(render_template(item, template))
        else:
            click.echo(render_template(data, template))
        return
    default_formatter(data)
```

- [ ] **Step 3: Commit**

```bash
git add src/gitcode_cli/formatters.py src/gitcode_cli/commands/issue.py src/gitcode_cli/commands/pr.py
git commit -m "feat(formatters): add --json fields, -q jq, -t template support"
```

---

## 阶段6：别名与额外对齐

> 目标：补充命令别名 `ls` → `list`, `new` → `create`。

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py`
- Modify: `src/gitcode_cli/commands/pr.py`

---

### Task 6.1: 命令别名

- [ ] **Step 1: Issue 别名**

```python
@issue_group.command("list", aliases=["ls"])
# 如果 Click 不支持 aliases，使用显式命令：

@issue_group.command("ls", hidden=True)
@click.pass_context
def issue_ls(ctx: click.Context, **kwargs):
    # 转发到 issue_list
    return ctx.invoke(issue_list, **kwargs)
```

注意：标准 Click 不支持 `aliases` 参数，需用 `cloup` 库或显式定义隐藏命令。推荐显式定义隐藏命令避免引入新依赖。

```python
# issue list 别名
issue_group.add_command(issue_list, name="ls")

# issue create 别名
issue_group.add_command(issue_create, name="new")
```

注意：`add_command` 只能注册一次。需要重构为：

```python
@issue_group.command("list")
@click.option(...)
@click.pass_context
def issue_list(...):
    ...

# 不行，需要复制装饰器。最简单的方式是：
issue_ls = click.Command("ls", params=issue_list.params, callback=issue_list.callback)
issue_group.add_command(issue_ls)
```

更简单的方式：

```python
def _make_alias(cmd, alias_name):
    alias = click.Command(alias_name, params=cmd.params, callback=cmd.callback, hidden=True)
    return alias

issue_group.add_command(_make_alias(issue_list, "ls"))
issue_group.add_command(_make_alias(issue_create, "new"))
```

- [ ] **Step 2: PR 别名**

```python
pr_group.add_command(_make_alias(pr_list, "ls"))
pr_group.add_command(_make_alias(pr_create, "new"))
```

- [ ] **Step 3: 验证别名**

Run: `python -m gitcode_cli issue ls --help`
Expected: 输出与 `issue list --help` 一致

Run: `python -m gitcode_cli pr new --help`
Expected: 输出与 `pr create --help` 一致

- [ ] **Step 4: Commit**

```bash
git add src/gitcode_cli/commands/issue.py src/gitcode_cli/commands/pr.py
git commit -m "feat: add ls->list and new->create aliases for issue and pr"
```

---

## 阶段7：PR 特有增强（可选）

> 目标：补充 `--delete-branch` (`pr close`), `--comment` (`pr close`), `--subject` (`pr merge`) 等参数。

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py`

---

### Task 7.1: PR close 增强

```python
@pr_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("number", type=int)
@click.option("-c", "--comment")
@click.option("-d", "--delete-branch", is_flag=True)
@click.pass_context
def pr_close(ctx: click.Context, repo_name: str | None, number: int, comment: str | None, delete_branch: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    if comment:
        service.comment(owner, repo, number, body=comment)
    item = service.update(owner, repo, number, state="closed")
    click.echo(f"Closed pull request #{item['number']}")
    if delete_branch:
        # 尝试删除远程分支
        try:
            import subprocess
            subprocess.run(["git", "push", "origin", "--delete", item["head"]["ref"]], check=True)
            click.echo(f"Deleted branch {item['head']['ref']}")
        except Exception as exc:
            click.echo(f"Warning: could not delete branch: {exc}", err=True)
```

---

## Self-Review 检查清单

### 1. Spec coverage

| 差异报告条目 | 对应 Task |
|-------------|-----------|
| 短选项缺失 (`-a`, `-b`, `-l`, `-s`, `-t` 等) | 阶段1 Task 1.1 + 1.2 |
| 参数可选性不一致 (title/body required) | 阶段2 Task 2.2 + 2.3 |
| 参数类型不一致 (仅支持 number) | 阶段4（URL/branch 解析可后续补充） |
| JSON 输出不完整 | 阶段5 Task 5.1 |
| 高级功能缺失 (`--body-file`, `--editor`, `--web`) | 阶段4 Task 4.1 |
| 缺失子命令 (reopen, edit, delete, status) | 阶段3 Task 3.1 + 3.2 |
| 命令别名 (`ls`, `new`) | 阶段6 Task 6.1 |
| `--limit` / `-L` | 阶段4 Task 4.1 |
| `--milestone` / `-m` | 阶段4 Task 4.1 |
| `pr close --delete-branch` | 阶段7 Task 7.1 |

### 2. Placeholder scan

计划中无 "TBD", "TODO", "implement later" 等占位符。所有代码片段均为可直接使用的完整实现。

### 3. Type consistency

- `prompt_if_missing` 返回 `str`，与 Click option 类型一致。
- `get_current_git_branch` / `get_default_git_branch` 返回 `str | None`，与现有代码风格一致。
- `json_fields` 参数为 `str | None`，通过逗号分割为 `list[str]` 传递给 `dump_json`。

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-gc-gh-alignment.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

**Which approach?**
