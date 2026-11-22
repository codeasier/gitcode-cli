from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from functools import partial
from itertools import islice
from typing import Any

import click

from ..cli_compat import get_body_from_options
from ..errors import APIError
from ..formatters import format_issue_detail, format_issue_list, output_result
from ..helptext import GCSectionGroup, set_gc_help
from ..repo import resolve_repo
from ..services.discussions import DiscussionService
from ..utils import safe_echo
from ._community_pages import page_rows

_LIST_FIELDS = (
    "number",
    "id",
    "title",
    "category",
    "author",
    "labels",
    "createdAt",
    "updatedAt",
    "closed",
    "answered",
    "locked",
)
_VIEW_FIELDS = (*_LIST_FIELDS, "body")
_REPO = click.option("-R", "--repo", "repo_name", help="GitCode repository in [HOST/]OWNER/REPO format.")
_BODY = click.option("-b", "--body", help="Markdown text.")
_BODY_FILE = click.option("-F", "--body-file", help="UTF-8 file containing Markdown, or '-' for stdin.")
_LIMIT = click.option("-L", "--limit", type=click.IntRange(min=1), default=30, show_default=True)
_NUMBER = click.argument("number", type=click.IntRange(min=1))
_JSON = click.option("--json", "json_fields", help="Print the named JSON fields, separated by commas.")


def _service(ctx: click.Context, repo_name: str | None) -> DiscussionService:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    return DiscussionService(app.client(), owner, repo)


def _nonblank(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise click.UsageError(f"Provide a nonblank {label}.")
    return value


def _body(body: str | None, body_file: str | None) -> str:
    return _nonblank(get_body_from_options(body, body_file, False), "--body or --body-file")


def _validate_fields(fields: str | None, valid: tuple[str, ...]) -> None:
    if fields is not None and any(field.strip() not in valid for field in fields.split(",")):
        raise click.UsageError("Supported JSON fields: " + ", ".join(valid))


def _flag(value: Any) -> bool | None:
    if isinstance(value, (int, str)) and value in (0, 1, "0", "1"):
        return value in (1, "1")
    return None


def _project(row: dict) -> dict:
    closed = _flag(row.get("is_closed"))
    if closed is None:
        raise APIError("Missing or invalid discussion state in response.")
    if type(row.get("number")) is not int or row["number"] < 1:
        raise APIError("Missing or invalid discussion number in response.")
    for field in ("author", "category"):
        if row.get(field) is not None and not isinstance(row[field], dict):
            raise APIError("Invalid discussion author or category in response.")
    return {
        **{key: row.get(key) for key in ("id", "number", "author", "title", "category", "labels")},
        "closed": closed,
        "state": "CLOSED" if closed else "OPEN",
        "answered": _flag(row.get("is_answered")),
        "locked": _flag(row.get("is_lock")),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "body": row.get("md_content"),
    }


def _updated(row: dict) -> datetime:
    try:
        # Normalize offsets before comparing; sorting ISO text across timezones gives incorrect results.
        dt = datetime.fromisoformat(str(row["updatedAt"]).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise APIError("Missing or invalid discussion update timestamp; cannot sort by updated.") from None


def _matching(rows: Iterator[dict], state: str, category: str | None, author: str | None) -> Iterator[dict]:
    for raw in rows:
        row = _project(raw)
        if state != "all" and row["state"].lower() != state:
            continue
        if author and (row["author"] or {}).get("login") != author:
            continue
        if category and (row["category"] or {}).get("name") != category:
            continue
        yield row


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and value.isprintable()


def _unconfirmed_write() -> APIError:
    return APIError("GitCode did not confirm the write. Verify the remote state before retrying.")


def _confirm_discussion(result: Any, *, title: str, body: str, category: str, expected: int | None = None) -> int:
    if not isinstance(result, dict) or not _valid_id(result.get("id")):
        raise _unconfirmed_write()
    number = result.get("number")
    if type(number) is not int or number < 1 or (expected is not None and number != expected):
        raise _unconfirmed_write()
    returned_category = result.get("category")
    if (
        result.get("title") != title
        or result.get("md_content") != body
        or not isinstance(returned_category, dict)
        or returned_category.get("name") != category
    ):
        raise _unconfirmed_write()
    return number


def _discussion_id(service: DiscussionService, number: int) -> str:
    # The discussion number is repository-local; comment responses use the
    # opaque discuss_id instead. Map it once before changing remote state.
    result = service.get(number)
    if isinstance(result, dict) and type(result.get("number")) is int and result["number"] == number:
        identity = result.get("id")
        if isinstance(identity, str) and _valid_id(identity):
            return identity
    raise APIError("Unable to verify the target discussion; no comment was submitted.")


def _confirm_comment(result: Any, *, discussion_id: str, body: str) -> str:
    if not isinstance(result, dict):
        raise _unconfirmed_write()
    identity = result.get("id")
    if (
        not isinstance(identity, str)
        or not _valid_id(identity)
        or result.get("discuss_id") != discussion_id
        or result.get("md_content") != body
        or type(result.get("type")) is not int
        or result["type"] != 1  # GitCode distinguishes a top-level comment from a reply (2).
    ):
        raise _unconfirmed_write()
    return identity


def _checked_comments(rows: Iterator[dict]) -> Iterator[dict]:
    for row in rows:
        author, body = row.get("author"), row.get("md_content")
        if (
            not _valid_id(row.get("id"))
            or (author is not None and not isinstance(author, dict))
            or (body is not None and not isinstance(body, str))
        ):
            raise APIError("Invalid discussion comment in GitCode response.")
        yield row


@click.group("discussion", cls=GCSectionGroup, help="Work with GitCode repository discussions.")
def discussion_group() -> None:
    pass


@discussion_group.command(
    "list", help="List repository discussions; by default show the most recently updated open ones."
)
@_REPO
@_LIMIT
@click.option("-s", "--state", type=click.Choice(["open", "closed", "all"]), default="open", show_default=True)
@click.option("-S", "--search", help="Search title and description on GitCode.")
@click.option("-c", "--category", help="Exact GitCode category name.")
@click.option("-A", "--author", help="Exact GitCode author login.")
@click.option("--sort", type=click.Choice(["created", "updated"]), default="updated", show_default=True)
@click.option("--order", type=click.Choice(["asc", "desc"]), default="desc", show_default=True)
@_JSON
@click.pass_context
def list_discussions(ctx, repo_name, limit, state, search, category, author, sort, order, json_fields):
    _validate_fields(json_fields, _LIST_FIELDS)
    service = _service(ctx, repo_name)
    params = {"sort": "created", "direction": order}
    if search:
        params["search"] = search
    # v5 cannot sort by update time. Scan fully (or fail), then apply the limit, never sort a truncated prefix.
    size = 100 if sort == "updated" or state != "all" or author or category else min(limit, 100)
    rows = page_rows(partial(service.list_page, **params), size, identity="number")
    matches = _matching(rows, state, category, author)
    if sort == "updated":
        result = sorted(matches, key=_updated, reverse=order == "desc")[:limit]
    else:
        result = list(islice(matches, limit))
    output_result(result, json_fields, None, None, lambda items: safe_echo(format_issue_list(items)) if items else None)


discussion_group.add_command(list_discussions, "ls")
set_gc_help(list_discussions, gc_json_fields=list(_LIST_FIELDS))


@discussion_group.command("view", help="Show a discussion by its positive repository number.")
@_NUMBER
@_REPO
@click.option("-c", "--comments", is_flag=True, help="Include top-level comments (not nested replies).")
@_LIMIT
@click.option("--order", type=click.Choice(["oldest", "newest"]), default="newest", show_default=True)
@_JSON
@click.pass_context
def view_discussion(ctx, number, repo_name, comments, limit, order, json_fields):
    _validate_fields(json_fields, (*_VIEW_FIELDS, "comments") if comments else _VIEW_FIELDS)
    service = _service(ctx, repo_name)
    raw = service.get(number)
    if not isinstance(raw, dict) or raw.get("number") != number:
        raise APIError("GitCode did not return the requested discussion number.")
    row = _project(raw)
    if comments:
        fetch = partial(service.comments_page, number, order="time_asc" if order == "oldest" else "time_desc")
        row["comments"] = list(islice(_checked_comments(page_rows(fetch, min(limit, 100))), limit))

    def display(item: dict) -> None:
        safe_echo(format_issue_detail(item))
        for entry in item.get("comments", []):
            safe_echo(f"\n{(entry.get('author') or {}).get('login', '')}: {entry.get('md_content') or ''}")

    output_result(row, json_fields, None, None, display)


set_gc_help(view_discussion, gc_json_fields=[*_VIEW_FIELDS, "comments (with --comments)"])


@discussion_group.command("create", help="Create a discussion in an existing GitCode category.")
@_REPO
@click.option("-t", "--title", required=True)
@click.option("-c", "--category", required=True, help="Existing category name (not a slug).")
@_BODY
@_BODY_FILE
@click.pass_context
def create_discussion(ctx, repo_name, title, category, body, body_file):
    text = _body(body, body_file)
    title, category = _nonblank(title, "--title"), _nonblank(category, "--category")
    result = _service(ctx, repo_name).create(title, text, category)
    confirmed = _confirm_discussion(result, title=title, body=text, category=category)
    safe_echo(f"Created discussion #{confirmed}")


@discussion_group.command(
    "edit", help="Replace title, body and category. GitCode requires all three; no implicit read/merge."
)
@_NUMBER
@_REPO
@click.option("-t", "--title", required=True)
@click.option("-c", "--category", required=True)
@_BODY
@_BODY_FILE
@click.pass_context
def edit_discussion(ctx, number, repo_name, title, category, body, body_file):
    text = _body(body, body_file)
    title, category = _nonblank(title, "--title"), _nonblank(category, "--category")
    result = _service(ctx, repo_name).edit(number, title, text, category)
    confirmed = _confirm_discussion(result, title=title, body=text, category=category, expected=number)
    safe_echo(f"Updated discussion #{confirmed}")


@discussion_group.command("comment", help="Add a top-level Markdown comment to a discussion.")
@_NUMBER
@_REPO
@_BODY
@_BODY_FILE
@click.pass_context
def comment_discussion(ctx, number, repo_name, body, body_file):
    text = _body(body, body_file)
    service = _service(ctx, repo_name)
    parent_id = _discussion_id(service, number)
    result = service.comment(number, text)
    confirmed = _confirm_comment(result, discussion_id=parent_id, body=text)
    safe_echo(f"Created comment {confirmed} on discussion #{number}")
