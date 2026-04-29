from __future__ import annotations

import json
import subprocess

import click

from ..cli_compat import (
    get_body_from_options,
    get_default_base_branch,
    get_fill_info,
    normalize_multi_values,
    resolve_pr_identifier_or_current_branch,
)
from ..formatters import format_pr_detail, format_pr_list, output_result
from ..repo import resolve_repo
from ..services import PullRequestService
from ..utils import (
    get_current_git_branch,
    open_in_browser,
    prompt_if_missing,
    read_body_file,
    resolve_pr_arg,
    safe_echo,
    safe_number,
)


@click.group("pr")
def pr_group() -> None:
    pass


@pr_group.command("list")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.option("-s", "--state")
@click.option("-A", "--author")
@click.option("-B", "--base")
@click.option("--assignee")
@click.option("--draft", is_flag=True, default=None)
@click.option("--head")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-S", "--search")
@click.option("-L", "--limit", type=int, default=30, show_default=True, help="Maximum number of items to fetch.")
@click.option("-w", "--web", is_flag=True, help="Open the pull requests list in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def pr_list(
    ctx: click.Context,
    repo_name: str | None,
    state: str | None,
    author: str | None,
    base: str | None,
    assignee: str | None,
    draft: bool | None,
    head: str | None,
    labels: tuple[str, ...] | None,
    search: str | None,
    limit: int | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/pulls")
        return
    service = PullRequestService(app.client())
    labels_str = normalize_multi_values(labels)
    items = service.list(
        owner,
        repo,
        state=state,
        author=author,
        base=base,
        assignee=assignee,
        draft=draft,
        head=head,
        labels=labels_str,
        search=search,
    )
    if limit is not None:
        items = items[:limit]

    def default_formatter(data):
        output = format_pr_list(data)
        if output:
            safe_echo(output)

    output_result(
        items,
        json_fields,
        jq_query,
        template,
        default_formatter=default_formatter,
    )


@pr_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-w", "--web", is_flag=True, help="Open the pull request in the web browser.")
@click.option("-c", "--comments", is_flag=True, help="View pull request comments.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def pr_view(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str | None,
    web: bool,
    comments: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    item = service.get(owner, repo, number)
    if web:
        open_in_browser(item["html_url"])
        return
    if comments:
        comment_items = service.list_comments(owner, repo, number)
        data = dict(item) if item else {}
        data["comments"] = comment_items

        def default_formatter(data: dict) -> None:
            safe_echo(format_pr_detail(data))
            if comment_items:
                safe_echo("\nComments:")
                for comment in comment_items:
                    safe_echo(f"- {comment.get('body') or ''}")

        output_result(
            data,
            json_fields,
            jq_query,
            template,
            default_formatter=default_formatter,
        )
        return
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: safe_echo(format_pr_detail(data)),
    )


@pr_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("--editor", is_flag=True)
@click.option("--fill", is_flag=True, help="Use commit info for title and body.")
@click.option("--fill-first", is_flag=True, help="Use first commit info for title and body.")
@click.option("--fill-verbose", is_flag=True, help="Use all commits for body description.")
@click.option("--dry-run", is_flag=True)
@click.option("-B", "--base")
@click.option("-H", "--head")
@click.option("-d", "--draft", is_flag=True)
@click.option("--milestone")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-r", "--reviewer", "reviewers", multiple=True)
@click.option("-a", "--assignee", "assignees", multiple=True)
@click.option("-w", "--web", is_flag=True, help="Open the pull request in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("--template", help="Format output using a Go template string.")
@click.pass_context
def pr_create(
    ctx: click.Context,
    repo_name: str | None,
    title: str | None,
    body: str | None,
    body_file: str | None,
    editor: bool,
    fill: bool,
    fill_first: bool,
    fill_verbose: bool,
    dry_run: bool,
    base: str | None,
    head: str | None,
    draft: bool,
    milestone: str | None,
    labels: tuple[str, ...] | None,
    reviewers: tuple[str, ...] | None,
    assignees: tuple[str, ...] | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
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

    fill_mode = None
    if fill_verbose:
        fill_mode = "verbose"
    elif fill_first:
        fill_mode = "first"
    elif fill:
        fill_mode = "last"

    if fill_mode:
        fill_title, fill_body = get_fill_info(fill_mode)
        if title is None:
            title = fill_title
        if body is None:
            body = fill_body

    title = prompt_if_missing(title, "Title")
    body = get_body_from_options(body=body, body_file=body_file, editor=editor)
    payload = {
        "title": title,
        "body": body,
        "base": base,
        "head": head,
        "draft": draft,
        "labels": normalize_multi_values(labels),
        "assignees": normalize_multi_values(assignees),
        "reviewers": normalize_multi_values(reviewers),
        "milestone": milestone,
    }
    if dry_run:
        safe_echo(json.dumps({k: v for k, v in payload.items() if v is not None}, indent=2, sort_keys=True))
        return
    service = PullRequestService(app.client())
    item = service.create(owner, repo, **payload)
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: safe_echo(
            data.get("html_url")
            or data.get("url")
            or (f"Created PR #{data['number']}" if "number" in data else "Created pull request")
        ),
    )


@pr_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-c", "--comment")
@click.option("-d", "--delete-branch", is_flag=True, help="Delete the remote branch after closing.")
@click.pass_context
def pr_close(
    ctx: click.Context, repo_name: str | None, identifier: str | None, comment: str | None, delete_branch: bool
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    pr_item = service.get(owner, repo, number) if delete_branch else None
    if comment:
        service.comment(owner, repo, number, body=comment)
    item = service.update(owner, repo, number, state="closed")
    if delete_branch:
        try:
            branch = (pr_item or item).get("head", {}).get("ref")
            if branch:
                subprocess.run(["git", "push", "origin", "--delete", branch], check=True)
                safe_echo(f"Deleted remote branch {branch}")
            else:
                safe_echo("Warning: could not determine branch to delete.", err=True)
        except Exception as exc:
            safe_echo(f"Warning: could not delete remote branch: {exc}", err=True)
    safe_echo(f"Closed pull request #{safe_number(item, number)}")


@pr_group.command("merge")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-m", "--merge", "merge_mode", flag_value="merge")
@click.option("-s", "--squash", "merge_mode", flag_value="squash")
@click.option("-r", "--rebase", "merge_mode", flag_value="rebase")
@click.option("-d", "--delete-branch", is_flag=True, help="Delete the remote branch after merge.")
@click.pass_context
def pr_merge(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str | None,
    merge_mode: str | None,
    delete_branch: bool,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    pr_item = service.get(owner, repo, number)
    item = service.merge(owner, repo, number, merge_method=merge_mode or "merge")
    safe_echo(item["message"])
    if delete_branch:
        try:
            branch = pr_item.get("head", {}).get("ref")
            if branch:
                subprocess.run(["git", "push", "origin", "--delete", branch], check=True)
                safe_echo(f"Deleted remote branch {branch}")
            else:
                safe_echo("Warning: could not determine branch to delete.", err=True)
        except Exception as exc:
            safe_echo(f"Warning: could not delete remote branch: {exc}", err=True)


@pr_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-e", "--editor", is_flag=True)
@click.option("-w", "--web", is_flag=True, help="Open the pull request in the web browser.")
@click.option("--path")
@click.option("--position", type=int)
@click.pass_context
def pr_comment(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str | None,
    body: str | None,
    body_file: str | None,
    editor: bool,
    web: bool,
    path: str | None,
    position: int | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    if web:
        pr_item = service.get(owner, repo, number)
        open_in_browser(pr_item["html_url"])
        return
    body = get_body_from_options(body=body, body_file=body_file, editor=editor)
    body = prompt_if_missing(body, "Body")
    item = service.comment(owner, repo, number, body=body, path=path, position=position)
    safe_echo(str(item["id"]))


@pr_group.command("review")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-a", "--approve", is_flag=True, help="Approve the pull request. GitCode maps this to its review API.")
@click.option("--body")
@click.option("--comment", is_flag=True, help="Leave a review comment. Downgrades to a PR comment on GitCode.")
@click.option("--request-changes", is_flag=True, help="Request changes. Downgrades to a PR comment on GitCode.")
@click.option("--force", is_flag=True, help="Force review handling when supported by GitCode.")
@click.pass_context
def pr_review(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str | None,
    approve: bool,
    body: str | None,
    comment: bool,
    request_changes: bool,
    force: bool,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)

    selected_modes = [approve, comment, request_changes]
    if sum(1 for selected in selected_modes if selected) != 1:
        raise click.ClickException("Specify exactly one of --approve, --comment, or --request-changes.")

    if comment or request_changes:
        if not body:
            raise click.ClickException("Body is required when using --comment or --request-changes.")
        item = service.comment(owner, repo, number, body=body)
        if comment:
            safe_echo("GitCode review API does not support comment reviews; posted a pull request comment instead.")
        else:
            safe_echo(
                "GitCode review API does not support request-changes reviews; posted a pull request comment instead."
            )
        safe_echo(f"Posted pull request comment {item['id']}")
        return

    item = service.review(owner, repo, number, body=body, force=force)
    safe_echo(f"Reviewed pull request #{number}")


@pr_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.pass_context
def pr_reopen(ctx: click.Context, repo_name: str | None, identifier: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    item = service.update(owner, repo, number, state="open")
    safe_echo(f"Reopened pull request #{safe_number(item, number)}")


@pr_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-B", "--base")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label")
@click.option("-r", "--add-reviewer")
@click.option("--remove-assignee")
@click.option("--remove-label")
@click.option("--remove-reviewer")
@click.option("-m", "--milestone")
@click.option("--remove-milestone", is_flag=True, help="Remove the milestone from the pull request.")
@click.pass_context
def pr_edit(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str | None,
    title: str | None,
    body: str | None,
    body_file: str | None,
    base: str | None,
    add_assignee: str | None,
    add_label: str | None,
    add_reviewer: str | None,
    remove_assignee: str | None,
    remove_label: str | None,
    remove_reviewer: str | None,
    milestone: str | None,
    remove_milestone: bool,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    number = int(number)
    if body_file:
        body = read_body_file(body_file)
    data = {
        k: v
        for k, v in {
            "title": title,
            "body": body,
            "base": base,
            "assignee": add_assignee,
            "labels": add_label,
            "reviewer": add_reviewer,
            "unassignee": remove_assignee,
            "unset_labels": remove_label,
            "unset_reviewer": remove_reviewer,
            "milestone": milestone,
        }.items()
        if v is not None
    }
    if remove_milestone:
        data["milestone"] = ""
    if not data:
        raise click.UsageError("must specify at least one field to edit")
    item = service.update(owner, repo, number, **data)
    safe_echo(f"Edited pull request #{safe_number(item, number)}")


@pr_group.command("diff")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.pass_context
def pr_diff(ctx: click.Context, repo_name: str | None, identifier: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    diff_text = service.diff(owner, repo, int(number))
    safe_echo(diff_text)


@pr_group.command("checkout")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("-b", "--branch", help="Local branch name to checkout into.")
@click.pass_context
def pr_checkout(ctx: click.Context, repo_name: str | None, identifier: str | None, branch: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    item = service.get(owner, repo, int(number))
    head_ref = item.get("head", {}).get("ref")
    if not head_ref:
        raise click.ClickException("Unable to determine PR branch.")
    local_branch = branch or head_ref
    try:
        subprocess.run(["git", "fetch", "origin", head_ref], check=True)
        subprocess.run(["git", "checkout", "-b", local_branch, f"origin/{head_ref}"], check=True)
        safe_echo(f"Checked out branch {local_branch}")
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"Git checkout failed: {exc}") from exc


@pr_group.command("ready")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier", required=False)
@click.option("--undo", is_flag=True, help="Convert a pull request to draft.")
@click.pass_context
def pr_ready(ctx: click.Context, repo_name: str | None, identifier: str | None, undo: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    resolved_identifier = resolve_pr_identifier_or_current_branch(identifier)
    owner, repo, number = resolve_pr_arg(resolved_identifier, owner, repo, service)
    item = service.update(owner, repo, int(number), draft=undo)
    if undo:
        safe_echo(f"Converted pull request #{safe_number(item, number)} to draft")
    else:
        safe_echo(f"Marked pull request #{safe_number(item, number)} as ready for review")


@pr_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.pass_context
def pr_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    items = service.list(owner, repo, state="open")
    safe_echo(
        f"Open pull requests in {owner}/{repo}  (GitCode API approximation -- user-specific filtering is not available)"
    )
    if items:
        for item in items:
            safe_echo(f"  #{safe_number(item, '?')}\t{item['state']}\t{item['title']}")
    else:
        safe_echo("  No open pull requests")


pr_group.add_command(pr_list, name="ls")
pr_group.add_command(pr_create, name="new")
