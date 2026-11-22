from __future__ import annotations

from itertools import islice

import click

from ..helptext import GCSectionGroup
from ..services.organizations import OrganizationService
from ..utils import safe_echo
from ._community_pages import page_rows


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
