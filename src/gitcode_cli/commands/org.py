from __future__ import annotations

import json
from itertools import islice

import click

from ..context import AppContext
from ..helptext import GCSectionGroup, set_gc_help
from ..services.dashboards import FIELDS, MAX_PAGE, MAX_PER_PAGE, dashboard_page
from ..services.organizations import OrganizationService
from ..utils import safe_echo
from ._community_pages import page_rows
from ._listing_output import selected_fields


@click.group("org", cls=GCSectionGroup, help="Work with GitCode organizations.")
def org_group() -> None:
    pass


@org_group.command("list", help="List organizations for the authenticated user.")
@click.option("-L", "--limit", type=click.IntRange(min=1), default=30, show_default=True)
@click.pass_context
def list_orgs(ctx: click.Context, limit: int) -> None:
    service = OrganizationService(ctx.obj["app"].client())
    rows = page_rows(service.list_page, min(limit, 100), identity="login")
    # Buffer validated output so an API failure is not mistaken for a shorter successful list.
    logins = [str(row["login"]) for row in islice(rows, limit)]
    if logins:
        safe_echo("\n".join(logins))


org_group.add_command(list_orgs, "ls")


@org_group.command("dashboards", help="List one page of GitCode organization Kanban boards (not GitHub Projects).")
@click.option(
    "--org", multiple=True, required=True, metavar="ORG", help="One organization slug, never inferred from git."
)
@click.option("--page", type=click.IntRange(1, MAX_PAGE), default=1, show_default=True)
@click.option("--per-page", type=click.IntRange(1, MAX_PER_PAGE), default=20, show_default=True)
@click.option("--json", "json_fields", metavar="FIELDS", help="Output only the selected comma-separated fields.")
@click.pass_context
def org_dashboards(ctx: click.Context, org: tuple[str, ...], page: int, per_page: int, json_fields: str | None) -> None:
    app: AppContext = ctx.obj["app"]
    if app.repo is not None:
        raise click.UsageError("Dashboards belong to an organization. Use --org without -R/--repo.")
    if len(org) != 1:
        raise click.UsageError("Supply exactly one --org.")
    fields = selected_fields(json_fields, FIELDS, None, None)
    rows = dashboard_page(org[0], page, per_page, token=app.token)
    if fields is not None:
        safe_echo(json.dumps([{key: row[key] for key in fields} for row in rows], indent=2))
    else:
        for row in rows:
            # Keep a single terminal-safe row even for names containing ESC, newlines or bidi controls.
            name = row["name"]
            safe_echo(f"{row['iid']}\t{name if name.isprintable() else json.dumps(name)}")


set_gc_help(org_dashboards, gc_json_fields=FIELDS, gc_examples=["gc org dashboards --org acme --json id,name"])
