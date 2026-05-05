# pygitcode

> A CLI tool for [GitCode](https://gitcode.com/) (`api.gitcode.com`), modeled after GitHub CLI (`gh`).

[![PyPI](https://img.shields.io/pypi/v/pygitcode)](https://pypi.org/project/pygitcode/)
[![Python](https://img.shields.io/pypi/pyversions/pygitcode)](https://pypi.org/project/pygitcode/)
[![License](https://img.shields.io/pypi/l/pygitcode)](https://github.com/codeasier/gitcode-cli/blob/main/LICENSE)

## Installation

```bash
pip install pygitcode
```

This exposes the `gc` (or `gitcode`) command in your shell.

## Windows PowerShell Users

On Windows PowerShell, `gc` is a built-in alias for the `Get-Content` cmdlet, which shadows the GitCode CLI. Use `gitcode` instead:

```powershell
gitcode auth login
gitcode issue list
gitcode pr list
```

Alternatively, you can remove or override the alias in your PowerShell profile:

```powershell
# Remove for the current session
Remove-Item Alias:gc -Force

# Or persist the override in your profile
Set-Alias -Name gc -Value 'C:\Users\<user>\AppData\Roaming\Python\Python313\Scripts\gc.exe'
```

## Quick Start

### Authentication

```bash
# Login with your GitCode personal access token
gc auth login

# Check auth status
gc auth status

# Print the current auth token
gc auth token

# Logout
gc auth logout

# Or set environment variable
export GC_TOKEN=your_token_here
```

### Issues

```bash
# List issues (with filtering options)
gc issue list
gc issue list --state closed --author @me
gc issue list --label bug --label "help wanted"
gc issue list --web    # Open in browser

# View an issue (with comments)
gc issue view 42
gc issue view 42 --comments
gc issue view 42 --web

# Create an issue
gc issue create -t "Bug report" -b "Something is broken"
gc issue create --label bug --label "help wanted"   # Multiple labels
gc issue create --web    # Create in browser

# Edit an issue (title, labels, assignee, milestone)
gc issue edit 42 -t "Updated title"
gc issue edit 42 --add-label bug --add-label docs
gc issue edit 42 --add-assignee @me
gc issue edit 42 --milestone v1.0 --remove-milestone

# Comment on an issue
gc issue comment 42 -b "Thanks for the report!"
gc issue comment 42 --editor    # Use system editor

gc issue delete 42              # Exposed for gh parity; GitCode API may reject deletion

# Close / reopen
gc issue close 42
gc issue close 42 -c "Fixed in #50" --reason completed
```

### Pull Requests

```bash
# List PRs (with filtering options)
gc pr list
gc pr list --state merged --author @me
gc pr list --base main --draft
gc pr list --web    # Open in browser

# View a PR (identifier optional - infers from current branch)
gc pr view           # View PR for current branch
gc pr view 42        # By number
gc pr view 42 --comments   # Include comments
gc pr view https://gitcode.com/owner/repo/pulls/42
gc pr view feature-branch

# Create a PR (auto-detects current branch and default base)
gc pr create -t "Add new feature"

# Create with auto-fill from commits
gc pr create --fill              # Use latest commit
gc pr create --fill-first        # Use first commit
gc pr create --fill-verbose      # Use all commits for body

# Create with editor
gc pr create --editor

# Preview without creating
gc pr create --dry-run

# Create in browser
gc pr create --web

# Close / merge / reopen (identifier optional)
gc pr close          # Close PR for current branch
gc pr close 42 -c "Closing as stale"
gc pr close --delete-branch    # Delete remote branch too

gc pr merge          # Merge PR for current branch
gc pr merge 42 -s    # Squash merge
gc pr merge --rebase
gc pr merge --delete-branch    # Delete remote branch after merge

# Edit a PR (add/remove labels, assignees, reviewers, milestones)
gc pr edit 42 -t "New title"
gc pr edit --add-label bug --remove-label "needs review"
gc pr edit --add-reviewer @me --remove-reviewer otheruser
gc pr edit --milestone v1.0 --remove-milestone

# Mark as ready or convert to draft
gc pr ready          # Mark current branch's PR as ready
gc pr ready --undo   # Convert back to draft

# Comment / review / diff (identifier optional)
gc pr comment -b "LGTM"
gc pr comment --path src/file.py --position 5 -b "Suggestion"
gc pr comment --body-file comment.txt
gc pr comment --editor

gc pr review --approve
gc pr review --comment -b "Looks good but needs tests"
gc pr review --request-changes -b "Missing documentation"

gc pr diff           # View diff for current branch's PR
gc pr diff 42

# Checkout a PR (identifier optional)
gc pr checkout        # Checkout PR for current branch? (prompts if ambiguous)
gc pr checkout 42
gc pr checkout -b local-branch-name
```

### Global Options

```bash
# Use a different repo without cd-ing into it
gc issue list -R owner/repo
gc pr list -R owner/repo

# Output as JSON with field selection
gc issue list --json number,title,state,author
gc pr list --json number,title,state,head,base

# Filter with jq
gc issue list -q '.[] | select(.state == "open")'
gc pr list -q '.[] | select(.draft == true)'

# Format with Go-style templates
gc issue list -t '{{.number}} {{.title}} ({{.state}})'
gc pr view -t 'PR #{{.number}}: {{.title}}\n{{.body}}'

# Open in browser
gc issue view 42 -w
gc pr view -w
```

## Documentation

- [Documentation index](docs/index.md)
- [Development guide](docs/development.md)

## Alignment with `gh` CLI

`pygitcode` aims to be as familiar as possible to `gh` users:

| Feature | `gh` | `gc` |
|---------|------|------|
| PR identifier optional (current branch inference) | ✅ | ✅ |
| `--fill` / `--fill-first` / `--fill-verbose` | ✅ | ✅ |
| `--editor` | ✅ | ✅ |
| `--dry-run` | ✅ | ✅ |
| `--web` (create/view in browser) | ✅ | ✅ |
| `--remove-*` flags for edit commands | ✅ | ✅ |
| `pr ready --undo` (convert to draft) | ✅ | ✅ |
| `pr review --request-changes` | ✅ | ✅ (fallback) |
| `--json fields` | ✅ | ✅ |
| `-q jq` filtering | ✅ | ✅ |
| `-t template` formatting | ✅ | ✅ |
| Command aliases (`ls` → `list`, `new` → `create`) | ✅ | ✅ |
| Multi-value options (`--label bug --label feature`) | ✅ | ✅ |

### Known Limitations (GitCode API differences)

- **PR comment model**: GitCode uses `path + position`, not GitHub's `line/side/commit`
- **PR review**: GitCode review API differs from GitHub; `--request-changes` falls back to PR comments
- **Issue deletion**: `gc issue delete` is exposed for CLI parity, but GitCode API does not support deleting issues
- **Issue create/update API**: GitCode puts `repo` in request body, not URL path

## License

MIT
