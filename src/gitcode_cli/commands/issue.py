from __future__ import annotations

import click

from ..formatters import output_result
from ..repo import resolve_repo
from ..services import IssueService
from ..utils import open_in_browser, prompt_if_missing, read_body_file, resolve_issue_arg


def _echo_issue_summary(items: list[dict]) -> None:
    for item in items:
        click.echo(f"#{item['number']}\t{item['state']}\t{item['title']}")


@click.group("issue")
def issue_group() -> None:
    pass


@issue_group.command("list")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-s", "--state")
@click.option("-l", "--label", "labels")
@click.option("-A", "--author")
@click.option("-a", "--assignee")
@click.option("-S", "--search")
@click.option("-L", "--limit", type=int, help="Maximum number of items to fetch.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def issue_list(
    ctx: click.Context,
    repo_name: str | None,
    state: str | None,
    labels: str | None,
    author: str | None,
    assignee: str | None,
    search: str | None,
    limit: int | None,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    items = service.list(owner, repo, state=state, labels=labels, creator=author, assignee=assignee, search=search)
    if limit is not None:
        items = items[:limit]
    output_result(
        items,
        json_fields,
        jq_query,
        template,
        default_formatter=_echo_issue_summary,
    )


@issue_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-w", "--web", is_flag=True, help="Open the issue in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def issue_view(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
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


@issue_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--assignee")
@click.option("-l", "--label", "labels")
@click.option("-m", "--milestone")
@click.option("-F", "--body-file")
@click.option("-w", "--web", is_flag=True, help="Open the issue in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("--template", help="Format output using a Go template string.")
@click.pass_context
def issue_create(
    ctx: click.Context,
    repo_name: str | None,
    title: str | None,
    body: str | None,
    assignee: str | None,
    labels: str | None,
    milestone: str | None,
    body_file: str | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues/new")
        return
    title = prompt_if_missing(title, "Title")
    if body_file:
        body = read_body_file(body_file)
    service = IssueService(app.client())
    item = service.create(owner, repo, title=title, body=body, assignee=assignee, labels=labels, milestone=milestone)
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: click.echo(data["html_url"]),
    )


@issue_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.pass_context
def issue_close(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    item = service.update(owner, repo, number, state="closed")
    click.echo(f"Closed issue #{item['number']}")


@issue_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-b", "--body")
@click.pass_context
def issue_comment(ctx: click.Context, repo_name: str | None, identifier: str, body: str | None) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    body = prompt_if_missing(body, "Body")
    service = IssueService(app.client())
    item = service.comment(owner, repo, number, body)
    click.echo(str(item["id"]))


@issue_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.pass_context
def issue_reopen(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    item = service.update(owner, repo, number, state="open")
    click.echo(f"Reopened issue #{item['number']}")


@issue_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label")
@click.option("--remove-assignee")
@click.option("--remove-label")
@click.pass_context
def issue_edit(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    title: str | None,
    body: str | None,
    add_assignee: str | None,
    add_label: str | None,
    remove_assignee: str | None,
    remove_label: str | None,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
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
    if not data:
        raise click.UsageError("must specify at least one field to edit")
    item = service.update(owner, repo, number, **data)
    click.echo(f"Edited issue #{item['number']}")


@issue_group.command("delete")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.confirmation_option(prompt="Are you sure you want to delete this issue?")
@click.pass_context
def issue_delete(ctx: click.Context, repo_name: str | None, identifier: str) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    service.delete(owner, repo, number)
    click.echo(f"Deleted issue #{number}")


@issue_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.pass_context
def issue_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    items = service.list(owner, repo, state="open")
    click.echo("GitCode-limited approximation of gh issue status")
    click.echo(f"Repository open issues for {owner}/{repo}:")
    for item in items:
        click.echo(f"  #{item['number']}\t{item['state']}\t{item['title']}")


issue_group.add_command(issue_list, name="ls")
issue_group.add_command(issue_create, name="new")
