from __future__ import annotations

import click

from ..cli_compat import get_body_from_options, normalize_multi_values
from ..formatters import format_issue_detail, format_issue_list, output_result
from ..repo import resolve_repo
from ..services import IssueService
from ..utils import (
    open_in_browser,
    prompt_if_missing,
    require_issue_number,
    resolve_issue_arg,
    safe_echo,
    safe_number,
)


def _echo_issue_summary(items: list[dict]) -> None:
    output = format_issue_list(items)
    if output:
        safe_echo(output)


@click.group("issue")
def issue_group() -> None:
    pass


@issue_group.command("list")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.option("-s", "--state")
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-A", "--author")
@click.option("-a", "--assignee")
@click.option("--milestone")
@click.option("--mention")
@click.option("-S", "--search")
@click.option("-L", "--limit", type=int, default=30, show_default=True, help="Maximum number of items to fetch.")
@click.option("-w", "--web", is_flag=True, help="Open the issue list in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def issue_list(
    ctx: click.Context,
    repo_name: str | None,
    state: str | None,
    labels: tuple[str, ...] | None,
    author: str | None,
    assignee: str | None,
    milestone: str | None,
    mention: str | None,
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
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues")
        return
    service = IssueService(app.client())
    labels_str = normalize_multi_values(labels)
    items = service.list(
        owner,
        repo,
        state=state,
        labels=labels_str,
        creator=author,
        assignee=assignee,
        milestone=milestone,
        mention=mention,
        search=search,
    )
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
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier")
@click.option("-w", "--web", is_flag=True, help="Open the issue in the web browser.")
@click.option("-c", "--comments", is_flag=True, help="View issue comments.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def issue_view(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    web: bool,
    comments: bool,
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
        number = require_issue_number(identifier)
    if web:
        target_url = identifier if url_owner else f"https://gitcode.com/{owner}/{repo}/issues/{number}"
        open_in_browser(target_url)
        return
    service = IssueService(app.client())
    item = service.get(owner, repo, number)
    if comments:
        comment_items = service.list_comments(owner, repo, number)
        data = dict(item) if item else {}
        data["comments"] = comment_items

        def default_formatter(data: dict) -> None:
            safe_echo(format_issue_detail(data))
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
        default_formatter=lambda data: safe_echo(format_issue_detail(data)),
    )


@issue_group.command("create")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--assignee")
@click.option("-l", "--label", "labels", multiple=True)
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
    labels: tuple[str, ...] | None,
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
    if len(title) > 255:
        raise click.ClickException("title must be 255 characters or fewer")
    body = get_body_from_options(body=body, body_file=body_file, editor=False)
    labels_str = normalize_multi_values(labels)
    service = IssueService(app.client())
    item = service.create(
        owner, repo, title=title, body=body, assignee=assignee, labels=labels_str, milestone=milestone
    )
    output_result(
        item,
        json_fields,
        jq_query,
        template,
        default_formatter=lambda data: safe_echo(data["html_url"]),
    )


@issue_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier")
@click.option("-c", "--comment", help="Leave a closing comment.")
@click.option("-r", "--reason", type=click.Choice(["completed", "not_planned"]), help="Reason for closing.")
@click.pass_context
def issue_close(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    comment: str | None,
    reason: str | None,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    if comment:
        service.comment(owner, repo, number, comment)
    update_data: dict = {"state": "closed"}
    if reason:
        update_data["state_reason"] = reason
    item = service.update(owner, repo, number, **update_data)
    safe_echo(f"Closed issue #{safe_number(item, number)}")


@issue_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
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
    safe_echo(f"Reopened issue #{safe_number(item, number)}")


@issue_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label", "add_labels", multiple=True)
@click.option("-m", "--milestone")
@click.option("--remove-milestone", is_flag=True, help="Remove the milestone from the issue.")
@click.pass_context
def issue_edit(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    title: str | None,
    body: str | None,
    body_file: str | None,
    add_assignee: str | None,
    add_labels: tuple[str, ...] | None,
    milestone: str | None,
    remove_milestone: bool,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    body = get_body_from_options(body=body, body_file=body_file, editor=False)
    data = {
        k: v
        for k, v in {
            "title": title,
            "body": body,
            "assignee": add_assignee,
            "labels": normalize_multi_values(add_labels),
            "milestone": milestone,
        }.items()
        if v is not None
    }
    if remove_milestone:
        data["milestone"] = ""
    if not data:
        raise click.UsageError("must specify at least one field to edit")
    service = IssueService(app.client())
    item = service.update(owner, repo, number, **data)
    safe_echo(f"Edited issue #{safe_number(item, number)}")


@issue_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-e", "--editor", is_flag=True)
@click.option("-w", "--web", is_flag=True)
@click.pass_context
def issue_comment(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    body: str | None,
    body_file: str | None,
    editor: bool,
    web: bool,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    if web:
        target_url = identifier if url_owner else f"https://gitcode.com/{owner}/{repo}/issues/{number}"
        open_in_browser(target_url)
        return
    body = get_body_from_options(body=body, body_file=body_file, editor=editor)
    body = prompt_if_missing(body, "Comment")
    service = IssueService(app.client())
    item = service.comment(owner, repo, number, body)
    safe_echo(item.get("html_url") or f"Commented on issue #{number}")


@issue_group.command("delete")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
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
    safe_echo(f"Deleted issue #{number}")


@issue_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.pass_context
def issue_status(ctx: click.Context, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    items = service.list(owner, repo, state="open")
    safe_echo("GitCode-limited approximation of gh issue status")
    safe_echo(f"Repository open issues for {owner}/{repo}:")
    for item in items:
        safe_echo(f"  #{safe_number(item, '?')}\t{item['state']}\t{item['title']}")


@issue_group.command("develop")
@click.option("-R", "--repo", "repo_name", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.argument("identifier")
@click.option("-b", "--base", help="Base branch for the develop branch.")
@click.option("-n", "--name", help="Name for the local branch.")
@click.pass_context
def issue_develop(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    base: str | None,
    name: str | None,
) -> None:
    if base is not None or name is not None:
        raise click.UsageError("--base and --name are not supported by 'gc issue develop'")

    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
    safe_echo("Note: 'issue develop' does not create a local branch on GitCode.")
    safe_echo(f"Opening issue #{number} in the browser instead.")
    open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues/{number}")


issue_group.add_command(issue_list, name="ls")
issue_group.add_command(issue_create, name="new")
