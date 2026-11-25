"""Manage the repository's task-label catalog, not the labels attached to a single issue."""

from __future__ import annotations

import re
import secrets

import click

from ..adapters.labels import clone_labels, upsert_label
from ..helptext import GCSectionGroup, set_gc_help
from ..repo import resolve_repo
from ..services.label_order import name_ordered_labels
from ..services.labels import LabelService, validate_name
from ..utils import safe_echo
from ._listing_output import listing_options, render_listing, selected_fields

_LABEL_FIELDS = ("id", "name", "color")


def _color(value):
    if value is None:
        return None
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
    if not match:
        raise click.BadParameter("Use a 6-digit RGB hex value, e.g. 0969DA.", param_hint="--color")
    return "#" + match[1].upper()


def _service(ctx, repo):
    app = ctx.obj["app"]
    owner, name = resolve_repo(repo or app.repo)
    return LabelService(app.client(), owner, name)


def _repo_opt(f):
    return click.option("--repo", "-R", help="Select a [HOST/]OWNER/REPO.")(f)


@click.group("label", cls=GCSectionGroup, help="Manage repository task labels in GitCode.")
def label_group():
    pass


@label_group.command("list")
@_repo_opt
@click.option("--limit", "-L", default=30, type=click.IntRange(1, 10000), show_default=True, help="Maximum results.")
@click.option("--search", "-S", default=None, help="Match text in the label name (case-insensitive).")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(["name"]),
    help="Sort up to 1,000 catalog labels by Unicode name; not with --search.",
)
@click.option("--order", type=click.Choice(["asc", "desc"]), help="Direction for --sort name (default: asc).")
@listing_options
@click.pass_context
def label_list(ctx, repo, limit, search, sort_by, order, json_fields, jq_query, template):
    """List task labels, optionally filtering their names."""
    fields = selected_fields(json_fields, _LABEL_FIELDS, jq_query, template)
    if sort_by is None:
        if order is not None:
            raise click.UsageError("--order requires --sort name; ordering by creation time is not supported.")
        labels = _service(ctx, repo).list(limit, search or "")
    else:
        if search is not None:
            raise click.UsageError("Use --sort name or --search, not both.")
        app = ctx.obj["app"]
        if repo == "" or app.repo == "":
            raise click.UsageError("Specify a nonempty repository for sorted label listing.")
        owner, name = resolve_repo(repo if repo is not None else app.repo)
        if repo is not None and app.repo is not None:
            global_owner, global_name = resolve_repo(app.repo)
            if not all(x.isascii() for x in (owner, name, global_owner, global_name)) or (
                owner.lower(),
                name.lower(),
            ) != (global_owner.lower(), global_name.lower()):
                raise click.UsageError("Global and label list repository selectors must identify the same repository.")
        labels = name_ordered_labels(owner, name, token=app.token, descending=order == "desc", limit=limit)
    rows = [{"id": x.get("id"), "name": x["name"], "color": (x.get("color") or "").lstrip("#")} for x in labels]

    def display(data):
        for row in data:
            safe_echo(f"{row['name']}\t{row['color']}")

    render_listing(rows, fields, jq_query, template, display)


@label_group.command("create")
@click.argument("name")
@_repo_opt
@click.option("--color", "-c", help="6-digit RGB hex; generated for new labels if omitted.")
@click.option("--force", "-f", is_flag=True, help="Update the color if a label already exists.")
@click.pass_context
def label_create(ctx, name, repo, color, force):
    """Create a task label (GitCode accepts name and color, not a description)."""
    validate_name(name)
    rgb = _color(color)
    default_color = "#" + secrets.token_hex(3).upper()
    service = _service(ctx, repo)
    if force:
        action = upsert_label(service, name, rgb, default_color)
    else:
        service.create(name, rgb or default_color)
        action = "Created"
    safe_echo(f"{action} label {name}")


@label_group.command("edit")
@click.argument("original")
@_repo_opt
@click.option("--name", "-n", help="New label name.")
@click.option("--color", "-c", help="New 6-digit RGB hex value.")
@click.pass_context
def label_edit(ctx, original, repo, name, color):
    """Rename a task label or update its color."""
    if name is None and color is None:
        raise click.UsageError("Specify --name or --color.")
    _service(ctx, repo).edit(original, name, _color(color))
    safe_echo(f"Updated label {name or original}")


@label_group.command("delete")
@click.argument("name")
@_repo_opt
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def label_delete(ctx, name, repo, yes):
    """Delete a task label from its repository, not just from one issue."""
    validate_name(name)
    owner, repo_name = resolve_repo(repo or ctx.obj["app"].repo)
    if not yes:
        click.confirm(f"Delete label {name} from {owner}/{repo_name}?", abort=True)
    LabelService(ctx.obj["app"].client(), owner, repo_name).delete(name)
    safe_echo(f"Deleted label {name}")


@label_group.command("clone")
@click.argument("source_repo", metavar="SOURCE-REPOSITORY")
@_repo_opt
@click.option("--force", "-f", is_flag=True, help="Update colors of existing labels; defaults to leaving them alone.")
@click.pass_context
def label_clone(ctx, source_repo, repo, force):
    """Copy labels from SOURCE-REPOSITORY to the selected repository; never remove destination labels."""
    source_target = resolve_repo(source_repo)
    dest_target = resolve_repo(repo or ctx.obj["app"].repo)
    if tuple(s.casefold() for s in source_target) == tuple(s.casefold() for s in dest_target):
        raise click.UsageError("Source and destination must be different repositories.")
    client = ctx.obj["app"].client()
    created, updated, kept = clone_labels(
        LabelService(client, *source_target), LabelService(client, *dest_target), force=force
    )
    safe_echo(f"Labels: {created} created, {updated} updated, {kept} kept.")


set_gc_help(label_list, gc_json_fields=_LABEL_FIELDS)
