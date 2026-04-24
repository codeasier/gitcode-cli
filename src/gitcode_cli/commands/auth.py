from __future__ import annotations

import click

from ..config import save_config


@click.group("auth")
def auth_group() -> None:
    pass


@auth_group.command("login")
@click.option("--with-token", is_flag=True, help="Read token from stdin is not implemented; prompt instead.")
def auth_login(with_token: bool) -> None:
    _ = with_token
    token = click.prompt("GitCode token", hide_input=True)
    save_config({"token": token})
    click.echo("Authentication saved.")
