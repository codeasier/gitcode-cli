from __future__ import annotations

import subprocess

import click

from ..formatters import output_result
from ..repo import resolve_repo
from ..services import PullRequestService
from ..utils import (
    get_current_git_branch,
    get_default_git_branch,
    open_in_browser,
    prompt_if_missing,
    read_body_file,
    resolve_pr_arg,
)


@click.group("pr")
def pr_group() -> None:
    pass


@pr_group.command("list")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-s", "--state")
@click.option("-A", "--author")
@click.option("-B", "--base")
@click.option("-l", "--label", "labels")
@click.option("-S", "--search")
@click.option("-L", "--limit", type=int, help="Maximum number of items to fetch.")
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
    labels: str | None,
    search: str | None,
    limit: int | None,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    items = service.list(owner, repo, state=state, author=author, base=base, labels=labels, search=search)
    if limit is not None:
        items = items[:limit]
    output_result(
        items,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: [
            click.echo(f"#{item['number']}\t{item['state']}\t{item['title']}") for item in data
        ],
    )


@pr_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-w", "--web", is_flag=True, help="Open the pull request in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def pr_view(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    item = service.get(owner, repo, number)
    if web:
        open_in_browser(item["html_url"])
        return
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: click.echo(f"#{data['number']} {data['title']}\n\n{data.get('body') or ''}"),
    )


@pr_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-B", "--base")
@click.option("-H", "--head")
@click.option("-d", "--draft", is_flag=True)
@click.option("-l", "--label", "labels")
@click.option("-r", "--reviewer")
@click.option("-a", "--assignee")
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
    base: str | None,
    head: str | None,
    draft: bool,
    labels: str | None,
    reviewer: str | None,
    assignee: str | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    if not head:
        head = get_current_git_branch()
        if not head:
            raise click.ClickException("Unable to detect current branch. Use --head.")
    if not base:
        base = get_default_git_branch()
    title = prompt_if_missing(title, "Title")
    if body_file:
        body = read_body_file(body_file)
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    item = service.create(
        owner,
        repo,
        title=title,
        body=body,
        base=base,
        head=head,
        draft=draft,
        labels=labels,
        assignees=assignee,
        reviewers=reviewer,
    )
    if web:
        open_in_browser(item["html_url"])
        return
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: click.echo(data["html_url"]),
    )


@pr_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-c", "--comment")
@click.option("-d", "--delete-branch", is_flag=True, help="Delete the local and remote branch after closing.")
@click.pass_context
def pr_close(
    ctx: click.Context, repo_name: str | None, identifier: str, comment: str | None, delete_branch: bool
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    if comment:
        service.comment(owner, repo, number, body=comment)
    item = service.update(owner, repo, number, state="closed")
    if delete_branch:
        try:
            branch = item.get("head", {}).get("ref")
            if branch:
                subprocess.run(["git", "push", "origin", "--delete", branch], check=True)
                click.echo(f"Deleted branch {branch}")
            else:
                click.echo("Warning: could not determine branch to delete.", err=True)
        except Exception as exc:
            click.echo(f"Warning: could not delete branch: {exc}", err=True)
    click.echo(f"Closed pull request #{item['number']}")


@pr_group.command("merge")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-m", "--merge", "merge_mode", flag_value="merge")
@click.option("-s", "--squash", "merge_mode", flag_value="squash")
@click.option("-r", "--rebase", "merge_mode", flag_value="rebase")
@click.pass_context
def pr_merge(ctx: click.Context, repo_name: str | None, identifier: str, merge_mode: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    item = service.merge(owner, repo, number, merge_method=merge_mode or "merge")
    click.echo(item["message"])


@pr_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-b", "--body")
@click.option("--path")
@click.option("--position", type=int)
@click.pass_context
def pr_comment(
    ctx: click.Context, repo_name: str | None, identifier: str, body: str | None, path: str | None, position: int | None
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    body = prompt_if_missing(body, "Body")
    item = service.comment(owner, repo, number, body=body, path=path, position=position)
    click.echo(str(item["id"]))


@pr_group.command("review")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-a", "--approve", is_flag=True, help="Approve the pull request. GitCode maps this to its review API.")
@click.option("--force", is_flag=True, help="Force review handling when supported by GitCode.")
@click.pass_context
def pr_review(ctx: click.Context, repo_name: str | None, identifier: str, approve: bool, force: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    if not approve:
        raise click.ClickException("Only --approve is currently supported because GitCode review API differs from gh.")
    item = service.review(owner, repo, number, force=force)
    click.echo(f"Reviewed pull request #{item['number']}")


@pr_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.pass_context
def pr_reopen(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    item = service.update(owner, repo, number, state="open")
    click.echo(f"Reopened pull request #{item['number']}")


@pr_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-B", "--base")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label")
@click.option("-r", "--add-reviewer")
@click.pass_context
def pr_edit(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    title: str | None,
    body: str | None,
    base: str | None,
    add_assignee: str | None,
    add_label: str | None,
    add_reviewer: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    number = int(number)
    data = {
        k: v
        for k, v in {
            "title": title,
            "body": body,
            "base": base,
            "assignee": add_assignee,
            "labels": add_label,
            "reviewer": add_reviewer,
        }.items()
        if v is not None
    }
    item = service.update(owner, repo, number, **data)
    click.echo(f"Edited pull request #{item['number']}")


@pr_group.command("diff")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.pass_context
def pr_diff(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    diff_text = service.diff(owner, repo, int(number))
    click.echo(diff_text)


@pr_group.command("checkout")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-b", "--branch", help="Local branch name to checkout into.")
@click.pass_context
def pr_checkout(ctx: click.Context, repo_name: str | None, identifier: str, branch: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    item = service.get(owner, repo, int(number))
    head_ref = item.get("head", {}).get("ref")
    if not head_ref:
        raise click.ClickException("Unable to determine PR branch.")
    local_branch = branch or head_ref
    try:
        subprocess.run(["git", "fetch", "origin", head_ref], check=True)
        subprocess.run(["git", "checkout", "-b", local_branch, f"origin/{head_ref}"], check=True)
        click.echo(f"Checked out branch {local_branch}")
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"Git checkout failed: {exc}") from exc


@pr_group.command("ready")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.pass_context
def pr_ready(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    owner, repo, number = resolve_pr_arg(identifier, owner, repo, service)
    item = service.update(owner, repo, int(number), draft=False)
    click.echo(f"Marked pull request #{item['number']} as ready for review")


@pr_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.pass_context
def pr_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = PullRequestService(app.client())
    # NOTE: GitCode API filter support is uncertain; list open PRs as fallback
    items = service.list(owner, repo, state="open")
    click.echo("Relevant pull requests in this repository:")
    for item in items:
        click.echo(f"  #{item['number']}\t{item['state']}\t{item['title']}")


pr_group.add_command(pr_list, name="ls")
pr_group.add_command(pr_create, name="new")
