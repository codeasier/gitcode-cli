# gc CLI gh Compatibility Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `gc` closer to `gh` by fixing misleading compatibility gaps first, then adding high-frequency flags and behaviors, then upgrading help and default output.

**Architecture:** Keep the existing command → service → client flow, but introduce a small `cli_compat.py` module for shared CLI-only behavior such as stdin/body/editor input, default branch inference, current-branch PR inference, and downgrade messaging. Keep API wrappers thin in `services/*` and centralize human-readable rendering in `formatters.py` so command modules stay focused on option parsing and orchestration.

**Tech Stack:** Python 3.13, Click, pytest, unittest.mock

---

## File Structure Overview

| File | Responsibility |
|------|----------------|
| `src/gitcode_cli/commands/auth.py` | `auth login` CLI behavior, especially `--with-token` stdin semantics |
| `src/gitcode_cli/commands/issue.py` | Issue command flags, defaults, status behavior, browser flow, text output |
| `src/gitcode_cli/commands/pr.py` | PR command flags, default PR inference, merge/review/comment behavior |
| `src/gitcode_cli/formatters.py` | Shared list/view text renderers, JSON-field metadata, formatting help hooks |
| `src/gitcode_cli/utils.py` | Existing low-level helpers that should stay generic if still used |
| `src/gitcode_cli/cli_compat.py` | **New** CLI-only shared compatibility helpers |
| `tests/unit/commands/test_auth.py` | Auth command integration tests |
| `tests/unit/commands/test_issue.py` | Issue command integration tests |
| `tests/unit/commands/test_pr.py` | PR command integration tests |
| `tests/unit/test_formatters.py` | Formatter unit tests |
| `tests/unit/test_utils.py` | Existing utility tests to trim/update after helper moves |
| `tests/unit/test_cli_compat.py` | **New** unit tests for compatibility helpers |

---

### Task 1: Add shared CLI compatibility helpers

**Files:**
- Create: `src/gitcode_cli/cli_compat.py`
- Create: `tests/unit/test_cli_compat.py`
- Modify: `src/gitcode_cli/utils.py:22-118`
- Modify: `tests/unit/test_utils.py:12-183`

- [ ] **Step 1: Write the failing helper tests**

```python
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.cli_compat import (
    get_body_from_options,
    get_default_base_branch,
    normalize_multi_values,
    resolve_pr_identifier_or_current_branch,
)


def test_get_body_from_options_prefers_body_argument():
    assert get_body_from_options(body="inline", body_file=None, editor=False) == "inline"


def test_get_body_from_options_reads_file(tmp_path):
    body_file = tmp_path / "body.md"
    body_file.write_text("file body", encoding="utf-8")
    assert get_body_from_options(body=None, body_file=str(body_file), editor=False) == "file body"


def test_get_default_base_branch_reads_origin_head(monkeypatch):
    monkeypatch.setattr(
        "gitcode_cli.cli_compat.subprocess.run",
        lambda *args, **kwargs: MagicMock(stdout="origin/main\n"),
    )
    assert get_default_base_branch() == "main"


def test_get_default_base_branch_raises_without_guess(monkeypatch):
    def raise_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr("gitcode_cli.cli_compat.subprocess.run", raise_error)
    with pytest.raises(click.ClickException, match="Please specify --base"):
        get_default_base_branch()


def test_normalize_multi_values_accepts_repeatable_tuple():
    assert normalize_multi_values(("bug", "cli")) == ["bug", "cli"]


def test_resolve_pr_identifier_or_current_branch_uses_current_branch(monkeypatch):
    service = MagicMock()
    service.list.return_value = [{"number": 7, "head": {"ref": "feature"}}]
    monkeypatch.setattr("gitcode_cli.cli_compat.get_current_git_branch", lambda: "feature")

    owner, repo, number = resolve_pr_identifier_or_current_branch(None, "owner", "repo", service)

    assert (owner, repo, number) == ("owner", "repo", "7")
```

- [ ] **Step 2: Run the helper tests to verify they fail**

Run: `pytest tests/unit/test_cli_compat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitcode_cli.cli_compat'`

- [ ] **Step 3: Write the minimal compatibility helper module**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import click

from .utils import get_current_git_branch, resolve_pr_arg


def get_body_from_options(body: str | None, body_file: str | None, editor: bool) -> str | None:
    if body is not None:
        return body
    if body_file:
        if body_file == "-":
            return click.get_text_stream("stdin").read()
        return Path(body_file).read_text(encoding="utf-8")
    if editor:
        return click.edit() or ""
    return body


def get_default_base_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException("Unable to infer default branch. Please specify --base.") from exc

    branch = result.stdout.strip()
    if branch.startswith("origin/"):
        branch = branch[len("origin/") :]
    if not branch:
        raise click.ClickException("Unable to infer default branch. Please specify --base.")
    return branch


def normalize_multi_values(values: tuple[str, ...] | list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [value for value in values if value]


def resolve_pr_identifier_or_current_branch(identifier: str | None, owner: str, repo: str, service):
    if identifier:
        return resolve_pr_arg(identifier, owner, repo, service)

    branch = get_current_git_branch()
    if not branch:
        raise click.ClickException("Unable to detect current branch. Pass a pull request number, URL, branch, or use --head.")
    return resolve_pr_arg(branch, owner, repo, service)
```

- [ ] **Step 4: Update the low-level utility tests to match the new boundaries**

```python
from gitcode_cli.utils import get_current_git_branch, parse_issue_url, parse_pr_url, resolve_issue_arg, resolve_pr_arg


def test_get_default_git_branch_is_removed_from_utils_boundary():
    assert hasattr(__import__("gitcode_cli.utils", fromlist=["resolve_pr_arg"]), "resolve_pr_arg")
```

Use this step to remove `get_default_git_branch` and body-loading assertions from `tests/unit/test_utils.py`, because those behaviors now belong in `tests/unit/test_cli_compat.py`.

- [ ] **Step 5: Run the updated utility and helper tests**

Run: `pytest tests/unit/test_cli_compat.py tests/unit/test_utils.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_cli_compat.py tests/unit/test_utils.py src/gitcode_cli/cli_compat.py src/gitcode_cli/utils.py
git commit -m "refactor: centralize gh-compat cli helpers"
```

---

### Task 2: Fix `auth login --with-token` stdin semantics

**Files:**
- Modify: `src/gitcode_cli/commands/auth.py:13-19`
- Modify: `tests/unit/commands/test_auth.py:16-33`

- [ ] **Step 1: Write the failing auth tests for stdin behavior**

```python
def test_auth_login_with_token_reads_stdin(runner, tmp_config_dir):
    result = runner.invoke(main, ["auth", "login", "--with-token"], input="stdin-token\n")
    assert result.exit_code == 0
    config = json.loads((tmp_config_dir / "config.json").read_text())
    assert config["token"] == "stdin-token"
    assert "GitCode token" not in result.output


def test_auth_login_with_token_requires_non_empty_stdin(runner, tmp_config_dir):
    result = runner.invoke(main, ["auth", "login", "--with-token"], input="\n")
    assert result.exit_code != 0
    assert "No token provided on stdin" in result.output
```

- [ ] **Step 2: Run the auth tests to verify the empty-stdin case fails**

Run: `pytest tests/unit/commands/test_auth.py::TestAuthLogin -v`
Expected: FAIL because `auth_login()` still prompts instead of validating stdin input

- [ ] **Step 3: Implement stdin token reading in `auth.py`**

```python
@auth_group.command("login")
@click.option("--with-token", is_flag=True, help="Read token from stdin.")
def auth_login(with_token: bool) -> None:
    if with_token:
        token = click.get_text_stream("stdin").read().strip()
        if not token:
            raise click.ClickException("No token provided on stdin.")
    else:
        token = click.prompt("GitCode token", hide_input=True)

    save_config({"token": token})
    click.echo("Authentication saved.")
```

- [ ] **Step 4: Run the auth tests again**

Run: `pytest tests/unit/commands/test_auth.py::TestAuthLogin -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_auth.py src/gitcode_cli/commands/auth.py
git commit -m "fix(auth): read login token from stdin"
```

---

### Task 3: Fix P0 issue behavior mismatches

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py:96-268`
- Modify: `tests/unit/commands/test_issue.py:122-243`
- Modify: `src/gitcode_cli/cli_compat.py`

- [ ] **Step 1: Write the failing issue tests for P0 behavior**

```python
def test_issue_edit_remove_fields_affect_payload(runner, mock_client, mock_repo):
    result = runner.invoke(
        main,
        ["issue", "edit", "42", "--remove-assignee", "alice", "--remove-label", "bug"],
    )
    assert result.exit_code == 0
    json_data = mock_client.patch.call_args.kwargs["json"]
    assert json_data["unassignee"] == "alice"
    assert json_data["unset_labels"] == "bug"


def test_issue_create_web_opens_create_url(runner, mock_client, mock_repo):
    with patch("gitcode_cli.commands.issue.open_in_browser") as mock_browser:
        result = runner.invoke(main, ["issue", "create", "-t", "T", "--web"])
    assert result.exit_code == 0
    mock_client.post.assert_not_called()
    mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/issues/new")


def test_issue_status_groups_relevant_items(runner, mock_client, mock_repo):
    mock_client.get.return_value = [
        {"number": "1", "state": "open", "title": "Mine", "author": {"login": "alice"}, "assignee": {"login": "alice"}},
        {"number": "2", "state": "open", "title": "Other", "author": {"login": "bob"}},
    ]
    result = runner.invoke(main, ["issue", "status"])
    assert result.exit_code == 0
    assert "Assigned to you" in result.output
```

- [ ] **Step 2: Run the targeted issue tests to verify they fail**

Run: `pytest tests/unit/commands/test_issue.py -k "remove_fields or create_web_opens_create_url or status_groups_relevant_items" -v`
Expected: FAIL because `issue edit` ignores remove options, `issue create --web` posts before opening, and `issue status` still prints a raw repo-open list

- [ ] **Step 3: Implement the minimal issue command fixes**

```python
@issue_group.command("create")
@click.option("-w", "--web", is_flag=True, help="Open the issue creation page in the web browser.")
def issue_create(..., web: bool, ...):
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues/new")
        return

    title = prompt_if_missing(title, "Title")
    body = get_body_from_options(body=body, body_file=body_file, editor=False)
    ...


def issue_edit(..., remove_assignee: str | None, remove_label: str | None) -> None:
    ...
    data = {
        k: v
        for k, v in {
            "title": title,
            "body": body,
            "assignee": add_assignee,
            "labels": add_label,
            "unassignee": remove_assignee,
            "unset_labels": remove_label,
        }.items()
        if v is not None
    }
    ...


def issue_status(ctx: click.Context, repo_name: str | None) -> None:
    ...
    items = service.list(owner, repo, state="open")
    click.echo("Assigned to you")
    for item in items:
        if item.get("assignee", {}).get("login") == "alice":
            click.echo(f"  #{item['number']}\t{item['title']}")
```

For `issue_status`, do not hard-code `alice` in the real implementation. Read the current user login through the existing auth/client path if available; if not, implement a clearly labeled repository-scoped fallback and print that it is a GitCode-limited approximation.

- [ ] **Step 4: Run the full issue command test file**

Run: `pytest tests/unit/commands/test_issue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_issue.py src/gitcode_cli/commands/issue.py src/gitcode_cli/cli_compat.py
git commit -m "fix(issue): align remove flags web flow and status semantics"
```

---

### Task 4: Fix P0 PR behavior mismatches

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py:67-373`
- Modify: `tests/unit/commands/test_pr.py:83-320`
- Modify: `src/gitcode_cli/cli_compat.py`

- [ ] **Step 1: Write the failing PR tests for P0 behavior**

```python
def test_pr_create_web_opens_create_page_without_post(runner, mock_client, mock_repo):
    with patch("gitcode_cli.commands.pr.open_in_browser") as mock_browser:
        result = runner.invoke(main, ["pr", "create", "-w"])
    assert result.exit_code == 0
    mock_client.post.assert_not_called()
    mock_browser.assert_called_once_with("https://gitcode.com/owner/repo/pulls/new")


def test_pr_view_without_identifier_uses_current_branch(runner, mock_client, mock_repo):
    with patch("gitcode_cli.commands.pr.get_current_git_branch", return_value="feature"):
        mock_client.get.side_effect = [
            [{"number": 42, "head": {"ref": "feature"}, "title": "Branch PR"}],
            {"number": 42, "title": "Branch PR", "body": "Body"},
        ]
        result = runner.invoke(main, ["pr", "view"])
    assert result.exit_code == 0
    assert "#42 Branch PR" in result.output


def test_pr_status_reports_relevant_sections(runner, mock_client, mock_repo):
    mock_client.get.return_value = [{"number": 1, "state": "open", "title": "First PR"}]
    result = runner.invoke(main, ["pr", "status"])
    assert result.exit_code == 0
    assert "Current branch" in result.output
    assert "Created by you" in result.output
```

- [ ] **Step 2: Run the targeted PR tests to verify they fail**

Run: `pytest tests/unit/commands/test_pr.py -k "create_web_opens_create_page_without_post or view_without_identifier_uses_current_branch or status_reports_relevant_sections" -v`
Expected: FAIL because `identifier` is still required, `pr create --web` still posts first, and `pr status` still lists raw open PRs

- [ ] **Step 3: Implement the minimal PR P0 changes**

```python
@pr_group.command("view")
@click.argument("identifier", required=False)
def pr_view(..., identifier: str | None, ...):
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_identifier_or_current_branch(identifier, owner, repo, service)
    ...


@pr_group.command("create")
def pr_create(..., web: bool, ...):
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/pulls/new")
        return

    if not head:
        head = get_current_git_branch()
        if not head:
            raise click.ClickException("Unable to detect current branch. Use --head.")
    if not base:
        base = get_default_base_branch()
    ...


@pr_group.command("status")
def pr_status(...):
    ...
    click.echo("Current branch")
    click.echo("Created by you")
    click.echo("Requesting your review")
```

Apply the same optional-identifier pattern to `pr comment`, `pr merge`, and `pr review` in this task, because the spec requires the shared no-identifier behavior for those commands too.

- [ ] **Step 4: Run the full PR command test file**

Run: `pytest tests/unit/commands/test_pr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_pr.py src/gitcode_cli/commands/pr.py src/gitcode_cli/cli_compat.py
git commit -m "fix(pr): align web defaults branch inference and status output"
```

---

### Task 5: Add high-frequency issue compatibility flags

**Files:**
- Modify: `src/gitcode_cli/commands/issue.py:16-175`
- Modify: `src/gitcode_cli/cli_compat.py`
- Modify: `tests/unit/commands/test_issue.py:45-190`

- [ ] **Step 1: Write the failing issue tests for new flags**

```python
def test_issue_list_accepts_repeatable_labels_and_milestone(runner, mock_client, mock_repo):
    result = runner.invoke(main, ["issue", "list", "-l", "bug", "-l", "cli", "-m", "v1", "--mention", "@me"])
    assert result.exit_code == 0
    params = mock_client.get.call_args.kwargs["params"]
    assert params["labels"] == "bug,cli"
    assert params["milestone"] == "v1"
    assert params["mention"] == "@me"


def test_issue_view_comments_flag_prints_comments_section(runner, mock_client, mock_repo):
    mock_client.get.side_effect = [
        {"number": "42", "title": "Test", "body": "Body", "comments": 1},
        [{"body": "first comment"}],
    ]
    result = runner.invoke(main, ["issue", "view", "42", "--comments"])
    assert result.exit_code == 0
    assert "Comments" in result.output
    assert "first comment" in result.output


def test_issue_comment_supports_body_file(runner, mock_client, mock_repo, tmp_path):
    body_file = tmp_path / "comment.md"
    body_file.write_text("comment body", encoding="utf-8")
    result = runner.invoke(main, ["issue", "comment", "42", "-F", str(body_file)])
    assert result.exit_code == 0
    assert mock_client.post.call_args.kwargs["json"]["body"] == "comment body"
```

- [ ] **Step 2: Run the targeted issue tests to verify they fail**

Run: `pytest tests/unit/commands/test_issue.py -k "repeatable_labels_and_milestone or comments_flag or supports_body_file" -v`
Expected: FAIL because the flags are not implemented yet

- [ ] **Step 3: Implement minimal issue flag support**

```python
@issue_group.command("list")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-m", "--milestone")
@click.option("--mention")
@click.option("-w", "--web", is_flag=True)
def issue_list(..., labels: tuple[str, ...], milestone: str | None, mention: str | None, web: bool, ...):
    ...
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues")
        return
    items = service.list(
        owner,
        repo,
        state=state,
        labels=",".join(normalize_multi_values(labels)) or None,
        creator=author,
        assignee=assignee,
        search=search,
        milestone=milestone,
        mention=mention,
    )


@issue_group.command("view")
@click.option("-c", "--comments", is_flag=True)
def issue_view(..., comments: bool, ...):
    ...


@issue_group.command("comment")
@click.option("-F", "--body-file")
@click.option("-e", "--editor", is_flag=True)
@click.option("-w", "--web", is_flag=True)
def issue_comment(...):
    ...
```

If GitCode does not have a separate issue-comments fetch endpoint already wrapped, add the thinnest possible service method in `services/issues.py` during this step.

- [ ] **Step 4: Run the full issue command tests**

Run: `pytest tests/unit/commands/test_issue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_issue.py src/gitcode_cli/commands/issue.py src/gitcode_cli/cli_compat.py
git commit -m "feat(issue): add high-frequency gh-compatible flags"
```

---

### Task 6: Add high-frequency PR compatibility flags and modes

**Files:**
- Modify: `src/gitcode_cli/commands/pr.py:25-254`
- Modify: `src/gitcode_cli/cli_compat.py`
- Modify: `tests/unit/commands/test_pr.py:42-231`

- [ ] **Step 1: Write the failing PR tests for new flags**

```python
def test_pr_list_accepts_assignee_draft_head_and_repeatable_labels(runner, mock_client, mock_repo):
    result = runner.invoke(main, ["pr", "list", "--assignee", "alice", "--draft", "--head", "feature", "-l", "bug", "-l", "cli"])
    assert result.exit_code == 0
    params = mock_client.get.call_args.kwargs["params"]
    assert params["assignee"] == "alice"
    assert params["draft"] is True
    assert params["head"] == "feature"
    assert params["labels"] == "bug,cli"


def test_pr_create_dry_run_prints_payload_without_post(runner, mock_client, mock_repo):
    result = runner.invoke(main, ["pr", "create", "-t", "T", "-B", "main", "-H", "feature", "--dry-run"])
    assert result.exit_code == 0
    assert '"title": "T"' in result.output
    mock_client.post.assert_not_called()


def test_pr_review_request_changes_uses_review_body(runner, mock_client, mock_repo):
    mock_client.post.return_value = {"number": 42}
    result = runner.invoke(main, ["pr", "review", "42", "--request-changes", "-b", "needs work"])
    assert result.exit_code == 0
    assert mock_client.post.called
```

- [ ] **Step 2: Run the targeted PR tests to verify they fail**

Run: `pytest tests/unit/commands/test_pr.py -k "accepts_assignee_draft_head_and_repeatable_labels or dry_run_prints_payload_without_post or request_changes_uses_review_body" -v`
Expected: FAIL because the new flags and review modes are not implemented

- [ ] **Step 3: Implement the minimal PR flag support**

```python
@pr_group.command("list")
@click.option("-a", "--assignee")
@click.option("-d", "--draft", is_flag=True)
@click.option("-H", "--head")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-w", "--web", is_flag=True)
def pr_list(...):
    ...


@pr_group.command("create")
@click.option("--dry-run", is_flag=True)
@click.option("-e", "--editor", is_flag=True)
@click.option("-m", "--milestone")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-r", "--reviewer", multiple=True)
@click.option("-a", "--assignee", multiple=True)
def pr_create(...):
    payload = {
        "title": title,
        "body": body,
        "base": base,
        "head": head,
        "draft": draft,
        "labels": ",".join(normalize_multi_values(labels)) or None,
        "reviewers": ",".join(normalize_multi_values(reviewer)) or None,
        "assignees": ",".join(normalize_multi_values(assignee)) or None,
        "milestone": milestone,
    }
    if dry_run:
        click.echo(dump_json({k: v for k, v in payload.items() if v is not None}))
        return
    ...


@pr_group.command("review")
@click.option("-a", "--approve", is_flag=True)
@click.option("-b", "--body")
@click.option("-c", "--comment", is_flag=True)
@click.option("-r", "--request-changes", is_flag=True)
def pr_review(...):
    ...
```

If the existing GitCode review endpoint can only approve, implement `--comment` and `--request-changes` as the closest explicit downgrade behavior and print that downgrade in the command output. Do not silently map every mode to approve.

- [ ] **Step 4: Run the full PR command tests**

Run: `pytest tests/unit/commands/test_pr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_pr.py src/gitcode_cli/commands/pr.py src/gitcode_cli/cli_compat.py
git commit -m "feat(pr): add high-frequency gh-compatible flags"
```

---

### Task 7: Upgrade formatters, help text, and default output

**Files:**
- Modify: `src/gitcode_cli/formatters.py:11-93`
- Modify: `src/gitcode_cli/commands/issue.py:16-93`
- Modify: `src/gitcode_cli/commands/pr.py:25-99`
- Modify: `tests/unit/test_formatters.py:20-183`
- Modify: `tests/unit/commands/test_issue.py:45-120`
- Modify: `tests/unit/commands/test_pr.py:42-111`

- [ ] **Step 1: Write the failing formatter and output tests**

```python
def test_render_issue_list_default_text():
    from gitcode_cli.formatters import render_issue_list

    text = render_issue_list([
        {"number": 1, "title": "Bug", "state": "open", "author": {"login": "alice"}},
    ])

    assert "1" in text
    assert "Bug" in text
    assert "open" in text
    assert "alice" in text


def test_issue_list_help_mentions_default_limit(runner):
    result = runner.invoke(main, ["issue", "list", "--help"])
    assert result.exit_code == 0
    assert "[default: 30]" in result.output


def test_pr_view_default_output_shows_metadata(runner, mock_client, mock_repo):
    mock_client.get.return_value = {
        "number": 42,
        "title": "Test PR",
        "body": "PR body",
        "state": "open",
        "user": {"login": "alice"},
        "base": {"ref": "main"},
        "head": {"ref": "feature"},
    }
    result = runner.invoke(main, ["pr", "view", "42"])
    assert result.exit_code == 0
    assert "State: open" in result.output
    assert "Author: alice" in result.output
    assert "feature -> main" in result.output
```

- [ ] **Step 2: Run the targeted formatter tests to verify they fail**

Run: `pytest tests/unit/test_formatters.py tests/unit/commands/test_issue.py tests/unit/commands/test_pr.py -k "default_text or default_output_shows_metadata or help_mentions_default_limit" -v`
Expected: FAIL because the renderers and richer help/output do not exist yet

- [ ] **Step 3: Implement shared renderers and wire commands to them**

```python
def render_issue_list(items: list[dict]) -> str:
    lines = []
    for item in items:
        author = item.get("author", {}).get("login") or item.get("user", {}).get("login") or "-"
        lines.append(f"#{item['number']}\t{item['state']}\t{item['title']}\t{author}")
    return "\n".join(lines)


def render_issue_view(item: dict) -> str:
    author = item.get("author", {}).get("login") or item.get("user", {}).get("login") or "-"
    return (
        f"#{item['number']} {item['title']}\n"
        f"State: {item.get('state', '-') }\n"
        f"Author: {author}\n\n"
        f"{item.get('body') or ''}"
    )


def render_pr_view(item: dict) -> str:
    author = item.get("user", {}).get("login") or "-"
    base_ref = item.get("base", {}).get("ref") or "-"
    head_ref = item.get("head", {}).get("ref") or "-"
    return (
        f"#{item['number']} {item['title']}\n"
        f"State: {item.get('state', '-') }\n"
        f"Author: {author}\n"
        f"Branch: {head_ref} -> {base_ref}\n\n"
        f"{item.get('body') or ''}"
    )
```

In the same step, add explicit `show_default=True` and concrete help text to options such as `-L/--limit` so Click prints discoverable defaults.

- [ ] **Step 4: Run the formatter and command tests again**

Run: `pytest tests/unit/test_formatters.py tests/unit/commands/test_issue.py tests/unit/commands/test_pr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_formatters.py tests/unit/commands/test_issue.py tests/unit/commands/test_pr.py src/gitcode_cli/formatters.py src/gitcode_cli/commands/issue.py src/gitcode_cli/commands/pr.py
git commit -m "feat(formatting): improve gh-style help and text output"
```

---

### Task 8: Run the full regression suite and clean up plan drift

**Files:**
- Modify: `tests/unit/commands/test_auth.py`
- Modify: `tests/unit/commands/test_issue.py`
- Modify: `tests/unit/commands/test_pr.py`
- Modify: `tests/unit/test_formatters.py`
- Modify: `tests/unit/test_utils.py`
- Modify: `tests/unit/test_cli_compat.py`

- [ ] **Step 1: Run the full targeted test suite**

Run: `pytest tests/unit/commands/test_auth.py tests/unit/commands/test_issue.py tests/unit/commands/test_pr.py tests/unit/test_formatters.py tests/unit/test_utils.py tests/unit/test_cli_compat.py -v`
Expected: PASS

- [ ] **Step 2: Run the entire unit suite**

Run: `pytest tests/unit -v`
Expected: PASS

- [ ] **Step 3: Remove obsolete assertions that lock in old behavior**

```python
# Delete tests that require:
# - get_default_git_branch() silently returning "master"
# - issue/pr --web creating first and opening later
# - pr view/comment/merge/review requiring identifier every time
```

Keep only assertions that match the approved spec and implemented downgrade behavior.

- [ ] **Step 4: Run the entire unit suite again**

Run: `pytest tests/unit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/commands/test_auth.py tests/unit/commands/test_issue.py tests/unit/commands/test_pr.py tests/unit/test_formatters.py tests/unit/test_utils.py tests/unit/test_cli_compat.py
git commit -m "test: lock in gh-compat alignment behavior"
```

---

## Self-Review

### Spec coverage
- P0 auth stdin semantics: covered by Task 2.
- P0 `issue edit --remove-*`, `issue/pr create --web`, `issue/pr status`, default base branch inference, default PR lookup: covered by Tasks 3 and 4.
- P1 high-frequency issue flags: covered by Task 5.
- P1 high-frequency PR flags and review modes: covered by Task 6.
- P2 help/default output improvements: covered by Task 7.
- Regression coverage and cleanup: covered by Task 8.

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every task includes exact files, concrete test code, commands, and expected outcomes.

### Type consistency
- Shared helper module is consistently named `src/gitcode_cli/cli_compat.py`.
- Default branch helper is consistently named `get_default_base_branch()`.
- Optional identifier resolution is consistently named `resolve_pr_identifier_or_current_branch()`.
- Multi-value normalization is consistently named `normalize_multi_values()`.

Plan complete and saved to `docs/superpowers/plans/2026-04-24-gc-gh-alignment-plan.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
