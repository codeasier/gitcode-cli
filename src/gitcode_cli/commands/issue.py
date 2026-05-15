from __future__ import annotations

import click

from ..adapters import IssueAdapter
from ..adapters.capabilities import capability_message, unsupported
from ..cli_compat import get_body_from_options
from ..formatters import format_issue_detail, format_issue_list, output_result
from ..helptext import GCSectionGroup, set_gc_help
from ..repo import resolve_repo
from ..services import IssueService, UserService
from ..utils import (
    open_in_browser,
    prompt_if_missing,
    read_template_file,
    require_issue_number,
    resolve_issue_arg,
    safe_echo,
    safe_number,
)


def _echo_issue_summary(items: list[dict]) -> None:
    output = format_issue_list(items)
    if output:
        safe_echo(output)


def _issue_status_labels(item: dict) -> str:
    labels = item.get("labels") or []
    if isinstance(labels, str):
        return labels
    names = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name") or label.get("title")
            if name:
                names.append(str(name))
        elif label:
            names.append(str(label))
    return ", ".join(names)


def _echo_issue_status(data: dict[str, list[dict]]) -> None:
    sections = [
        ("Issues assigned to you", data.get("assigned") or []),
        ("Issues mentioning you", data.get("mentioned") or []),
        ("Issues opened by you", data.get("createdBy") or []),
    ]
    for title, items in sections:
        safe_echo(title)
        if not items:
            safe_echo("  No issues found")
            safe_echo("")
            continue
        for item in items:
            labels = _issue_status_labels(item)
            created_at = item.get("created_at") or item.get("createdAt") or ""
            safe_echo(
                f"  #{safe_number(item, '?')}  {str(item.get('state') or '').upper()}  "
                f"{item.get('title') or ''}  {labels}  {created_at}".rstrip()
            )
        safe_echo("")


def _normalize_issue_state(state: object) -> object:
    if not isinstance(state, str):
        return state
    normalized = state.upper()
    if normalized == "OPENED":
        return "OPEN"
    return normalized


def _normalize_issue_number(number: object) -> object:
    if isinstance(number, str) and number.isdigit():
        return int(number)
    return number


def _normalize_issue_author(item: dict) -> object:
    author = item.get("author") or item.get("user") or item.get("creator")
    if not isinstance(author, dict):
        return author
    login = author.get("login") or author.get("username") or author.get("name")
    return {
        "id": author.get("id"),
        "is_bot": bool(author.get("is_bot", False)),
        "login": login,
        "name": author.get("name") or login,
    }


def _normalize_issue_list_items(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        normalized_item = dict(item)
        normalized_item["number"] = _normalize_issue_number(normalized_item.get("number"))
        normalized_item["state"] = _normalize_issue_state(normalized_item.get("state"))
        normalized_item["author"] = _normalize_issue_author(normalized_item)
        normalized.append(normalized_item)
    return normalized


def _pending_gh_compat(name: str) -> None:
    raise click.ClickException(f"gh-compatible command/flag '{name}' is recognized but not implemented yet.")


def _resolve_issue_target(app, repo_name: str | None, identifier: str) -> tuple[str, str, str, str | None]:
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        return url_owner, url_repo, number, identifier
    owner, repo = resolve_repo(repo_name or app.repo)
    return owner, repo, require_issue_number(identifier), None


def _validate_issue_comment_history_flags(
    *, create_if_none: bool, delete_last: bool, edit_last: bool, yes: bool
) -> None:
    if create_if_none and not edit_last:
        raise click.UsageError(capability_message("ISSUE_CREATE_IF_NONE_REQUIRES_EDIT_LAST"))
    if create_if_none and delete_last:
        raise click.UsageError(capability_message("ISSUE_CREATE_IF_NONE_REQUIRES_EDIT_LAST"))
    if yes and not delete_last:
        raise click.UsageError("--yes can only be used together with --delete-last.")
    if edit_last and delete_last:
        raise click.UsageError("Specify only one of --edit-last or --delete-last.")


def _validate_issue_comment_body_sources(*, body: str | None, body_file: str | None, editor: bool, web: bool) -> None:
    selected = [body is not None, body_file is not None, editor, web]
    if sum(selected) > 1:
        raise click.UsageError("specify only one of --body, --body-file, --editor, or --web")


def _issue_comment_url(owner: str, repo: str, number: str, item: dict | None) -> str:
    if item:
        if item.get("html_url"):
            return str(item["html_url"])
        comment_id = item.get("id")
        if comment_id is not None:
            return f"https://gitcode.com/{owner}/{repo}/issues/{number}#issuecomment-{comment_id}"
    return f"https://gitcode.com/{owner}/{repo}/issues/{number}"


def _handle_issue_comment_history(
    *,
    adapter: IssueAdapter,
    owner: str,
    repo: str,
    number: str,
    body: str | None,
    edit_last: bool,
    delete_last: bool,
    create_if_none: bool,
    yes: bool,
) -> None:
    if edit_last and body is None:
        raise click.UsageError("--body or --body-file is required when not running interactively")
    if delete_last and not yes and not click.confirm("Delete your last issue comment?", default=False):
        raise click.ClickException("Aborted.")
    result = adapter.manage_comment_history(
        owner,
        repo,
        number,
        body=body,
        delete_last=delete_last,
        create_if_none=create_if_none,
    )
    if result.message == "deleted":
        safe_echo(f"Deleted last comment on issue #{number}")
        return
    if result.message == "created":
        safe_echo(_issue_comment_url(owner, repo, number, result.item))
        return
    safe_echo(_issue_comment_url(owner, repo, number, result.item))


@click.group("issue", cls=GCSectionGroup, help="Work with GitCode issues.")
def issue_group() -> None:
    pass


@issue_group.command("list")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-s", "--state", type=click.Choice(["open", "closed", "all"]))
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-A", "--author")
@click.option("-a", "--assignee")
@click.option("--milestone")
@click.option("--mention")
@click.option("--app", help="Filter by app author. Unsupported on GitCode.")
@click.option("-S", "--search")
@click.option("-L", "--limit", type=int, default=30, show_default=True, help="Maximum number of items to fetch.")
@click.option("-w", "--web", is_flag=True, help="Open the issue list in the web browser.")
@click.option(
    "--json",
    "json_fields",
    is_flag=False,
    flag_value="",
    default=None,
    help="Output JSON. Optionally specify comma-separated fields.",
)
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
    app: str | None,
    search: str | None,
    limit: int | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app_ctx = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app_ctx.repo)
    if limit is not None and limit < 1:
        raise click.BadParameter("must be greater than 0", param_hint="--limit")
    if app is not None:
        raise unsupported("ISSUE_LIST_APP")
    if json_fields == "":
        safe_echo("Available fields: " + ", ".join(getattr(issue_list, "gc_json_fields", [])))
        raise click.exceptions.Exit(1)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues")
        return
    service = IssueService(app_ctx.client())
    adapter = IssueAdapter(service, UserService(app_ctx.client()))
    items = adapter.list_issues(
        owner,
        repo,
        state=state,
        labels=labels,
        author=author,
        assignee=assignee,
        milestone=milestone,
        mention=mention,
        search=search,
        limit=limit,
    )
    output_result(
        _normalize_issue_list_items(items) if json_fields or jq_query or template else items,
        json_fields,
        jq_query,
        template,
        default_formatter=_echo_issue_summary,
    )


@issue_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
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
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-a", "--assignee")
@click.option("-e", "--editor", is_flag=True)
@click.option("-l", "--label", "labels", multiple=True)
@click.option("-m", "--milestone")
@click.option("-F", "--body-file")
@click.option("-w", "--web", is_flag=True, help="Open the issue in the web browser.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-T", "--template", help="Template file to use as the issue body.")
@click.pass_context
def issue_create(
    ctx: click.Context,
    repo_name: str | None,
    title: str | None,
    body: str | None,
    assignee: str | None,
    editor: bool,
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
    if len(title) > 200:
        raise click.ClickException("title must be 200 characters or fewer")
    if template and (body is not None or body_file is not None or editor):
        raise click.UsageError("--template cannot be used with --body, --body-file, or --editor.")
    body = (
        read_template_file(template)
        if template
        else get_body_from_options(body=body, body_file=body_file, editor=editor)
    )
    if editor and body is None:
        raise click.ClickException("Editor was closed without saving an issue body.")
    if body is None:
        raise click.UsageError("--title and --body are required when not running interactively")
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    item = adapter.create_issue(
        owner,
        repo,
        title=title,
        body=body,
        assignee=assignee,
        labels=labels,
        milestone=milestone,
    )
    output_result(
        item,
        json_fields,
        jq_query,
        None,
        default_formatter=lambda data: safe_echo(data["html_url"]),
    )


@issue_group.command("close")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-c", "--comment", help="Leave a closing comment.")
@click.option("--duplicate-of", help="Close as a GitCode-limited duplicate approximation by posting a comment first.")
@click.option("-r", "--reason", type=click.Choice(["completed", "not_planned"]), help="Reason for closing.")
@click.pass_context
def issue_close(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    comment: str | None,
    duplicate_of: str | None,
    reason: str | None,
) -> None:
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
        number = require_issue_number(identifier)
    approximated = duplicate_of is not None
    if duplicate_of is not None:
        duplicate_comment = f"This issue is considered a duplicate of {duplicate_of}."
        comment = f"{comment}\n\n{duplicate_comment}" if comment else duplicate_comment
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    result = adapter.close_issue(owner, repo, number, comment=comment, reason=reason)
    approximation_note = (
        "Note: --duplicate-of is a GitCode-limited approximation; no native duplicate relationship was created."
    )
    if result.message == "already_closed_commented":
        safe_echo(f"Issue #{safe_number(result.item, number)} is already closed; posted comment")
        if approximated:
            safe_echo(approximation_note)
        return
    if result.message == "already_closed":
        safe_echo(f"Issue #{safe_number(result.item, number)} is already closed")
        return
    safe_echo(f"Closed issue #{safe_number(result.item, number)}")
    if approximated:
        safe_echo(approximation_note)


@issue_group.command("comment")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("--create-if-none", is_flag=True)
@click.option("--delete-last", is_flag=True)
@click.option("--edit-last", is_flag=True)
@click.option("-e", "--editor", is_flag=True)
@click.option("-w", "--web", is_flag=True)
@click.option("--yes", is_flag=True)
@click.pass_context
def issue_comment(
    ctx: click.Context,
    repo_name: str | None,
    identifier: str,
    body: str | None,
    body_file: str | None,
    create_if_none: bool,
    delete_last: bool,
    edit_last: bool,
    editor: bool,
    web: bool,
    yes: bool,
) -> None:
    app = ctx.obj["app"]
    _validate_issue_comment_body_sources(body=body, body_file=body_file, editor=editor, web=web)
    owner, repo, number, target_url = _resolve_issue_target(app, repo_name, identifier)
    if web:
        open_in_browser(target_url or f"https://gitcode.com/{owner}/{repo}/issues/{number}")
        return

    _validate_issue_comment_history_flags(
        create_if_none=create_if_none,
        delete_last=delete_last,
        edit_last=edit_last,
        yes=yes,
    )
    history_mode = edit_last or delete_last
    body = get_body_from_options(body=body, body_file=body_file, editor=editor)
    if editor and body is None:
        raise click.ClickException("Editor was closed without saving a comment.")

    service = IssueService(app.client())
    adapter = IssueAdapter(service, UserService(app.client()))

    if history_mode:
        _handle_issue_comment_history(
            adapter=adapter,
            owner=owner,
            repo=repo,
            number=number,
            body=body,
            edit_last=edit_last,
            delete_last=delete_last,
            create_if_none=create_if_none,
            yes=yes,
        )
        return

    body = prompt_if_missing(body, "Comment")
    item = adapter.comment_issue(owner, repo, number, body=body)
    safe_echo(_issue_comment_url(owner, repo, number, item))


@issue_group.command("reopen")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-c", "--comment")
@click.pass_context
def issue_reopen(ctx: click.Context, repo_name: str | None, identifier: str, comment: str | None) -> None:
    if comment is not None:
        _pending_gh_compat("issue reopen --comment")
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
        number = require_issue_number(identifier)
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    result = adapter.reopen_issue(owner, repo, number)
    if result.message == "already_open":
        safe_echo(f"Issue #{safe_number(result.item, number)} is already open")
        return
    safe_echo(f"Reopened issue #{safe_number(result.item, number)}")


@issue_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("identifier")
@click.option("-t", "--title")
@click.option("-b", "--body")
@click.option("-F", "--body-file")
@click.option("-a", "--add-assignee")
@click.option("-l", "--add-label", "add_labels", multiple=True)
@click.option("-m", "--milestone", type=int)
@click.option("--remove-assignee")
@click.option("--remove-label", "remove_labels", multiple=True)
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
    milestone: int | None,
    remove_assignee: str | None,
    remove_labels: tuple[str, ...] | None,
    remove_milestone: bool,
) -> None:
    if remove_assignee is not None:
        _pending_gh_compat("issue edit --remove-assignee")
    if remove_labels:
        _pending_gh_compat("issue edit --remove-label")
    app = ctx.obj["app"]
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
        number = require_issue_number(identifier)
    body = get_body_from_options(body=body, body_file=body_file, editor=False)
    if not any(
        [
            title is not None,
            body is not None,
            add_assignee is not None,
            add_labels,
            milestone is not None,
            remove_assignee is not None,
            remove_labels,
            remove_milestone,
        ]
    ):
        raise click.UsageError("must specify at least one field to edit")
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    item = adapter.edit_issue(
        owner,
        repo,
        number,
        title=title,
        body=body,
        add_assignee=add_assignee,
        add_labels=add_labels,
        milestone=milestone,
        remove_milestone=remove_milestone,
    )
    safe_echo(f"Edited issue #{safe_number(item, number)}")


@issue_group.command("delete")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.argument("identifier")
@click.pass_context
def issue_delete(ctx: click.Context, repo_name: str | None, identifier: str, yes: bool) -> None:
    app = ctx.obj["app"]
    owner, repo, number, _ = _resolve_issue_target(app, repo_name, identifier)
    target = f"{owner}/{repo}#{number}"
    if not yes and not click.confirm(f"Delete issue {target}?", default=False):
        raise click.ClickException("Aborted.")
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    adapter.delete_issue(owner, repo, number)
    safe_echo(f"Deleted issue {target}")


@issue_group.command("status")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("--json", "json_fields", help="Output JSON. Optionally specify comma-separated fields.")
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def issue_status(
    ctx: click.Context,
    repo_name: str | None,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    service = IssueService(app.client())
    adapter = IssueAdapter(service, UserService(app.client()))
    result = adapter.status(owner, repo)
    data = result.item or {"assigned": [], "mentioned": [], "createdBy": []}
    if json_fields or jq_query or template:
        output_result(data, json_fields, jq_query, template, default_formatter=_echo_issue_status)
        return
    safe_echo(f"Relevant issues in {owner}/{repo}")
    safe_echo("")
    if result.message:
        safe_echo(result.message)
        safe_echo("")
    _echo_issue_status(data)


@issue_group.command("develop")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
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
    app = ctx.obj["app"]
    if base is not None:
        raise unsupported("ISSUE_DEVELOP_BASE")
    if name is not None:
        raise unsupported("ISSUE_DEVELOP_NAME")
    url_owner, url_repo, number = resolve_issue_arg(identifier)
    if url_owner:
        assert url_repo is not None
        owner, repo = url_owner, url_repo
    else:
        owner, repo = resolve_repo(repo_name or app.repo)
        number = require_issue_number(identifier)
    service = IssueService(app.client())
    adapter = IssueAdapter(service)
    result = adapter.develop(owner, repo, number, base=base, name=name)
    if result.warning:
        safe_echo(result.warning)
    if result.message:
        safe_echo(result.message)
    open_in_browser(f"https://gitcode.com/{owner}/{repo}/issues/{number}")


issue_group.add_command(issue_list, name="ls")
issue_group.add_command(issue_create, name="new")

set_gc_help(
    issue_group,
    gc_usage="gc issue <command> [flags]",
    gc_command_sections=[
        ("GENERAL COMMANDS", ["create", "list", "status"]),
        ("TARGETED COMMANDS", ["close", "comment", "delete", "develop", "edit", "reopen", "view"]),
    ],
    gc_examples=[
        "gc issue list",
        "gc issue create --label bug",
        "gc issue view 123 --web",
    ],
    gc_arguments_help=[
        "An issue can be supplied as argument in any of the following formats:",
        '- by number, e.g. "123"; or',
        '- by URL, e.g. "https://gitcode.com/OWNER/REPO/issues/123".',
    ],
)

issue_list.short_help = "List issues in a repository"
issue_list.help = "List issues in a repository. By default, this only lists open issues."
set_gc_help(
    issue_list,
    gc_usage="gc issue list [flags]",
    gc_aliases=["ls"],
    gc_json_fields=[
        "author",
        "assignees",
        "body",
        "comments",
        "createdAt",
        "labels",
        "milestone",
        "number",
        "state",
        "title",
        "updatedAt",
        "url",
    ],
    gc_examples=[
        'gc issue list --label "bug" --label "help wanted"',
        "gc issue list --author monalisa",
        "gc issue list --assignee @me",
        'gc issue list --milestone "The big 1.0"',
        'gc issue list --search "error no:assignee sort:created-asc"',
        "gc issue list --state all",
    ],
)

issue_view.short_help = "View an issue"
issue_view.help = "View an issue."
issue_create.short_help = "Create a new issue"
issue_create.help = "Create a new issue."
set_gc_help(issue_create, gc_aliases=["new"])
issue_close.short_help = "Close issue"
issue_close.help = "Close issue."
issue_comment.short_help = "Add a comment to an issue"
issue_comment.help = "Add a comment to an issue."
set_gc_help(
    issue_comment,
    gc_examples=[
        'gc issue comment 123 --body "I have a question"',
        "gc issue comment 123 --body-file comment.md",
        "gc issue comment 123 --edit-last --body-file comment.md",
        "gc issue comment 123 --web",
    ],
)
issue_reopen.short_help = "Reopen issue"
issue_reopen.help = "Reopen issue."
issue_edit.short_help = "Edit issues"
issue_edit.help = "Edit issues."
issue_delete.short_help = "Delete issue"
issue_delete.help = "Delete issue."
issue_status.short_help = "Show status of relevant issues"
issue_status.help = "Show status of relevant issues."
issue_develop.short_help = "Manage linked branches for an issue"
issue_develop.help = "Manage linked branches for an issue."
