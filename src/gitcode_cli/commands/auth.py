from __future__ import annotations

import click

from ..config import save_config


@click.group("auth")
def auth_group() -> None:
    pass


@auth_group.command("login")
@click.option("--with-token", is_flag=True, help="Read token from stdin.")
def auth_login(with_token: bool) -> None:
    if with_token:
        token = click.get_text_stream("stdin").read().strip()
        if not token:
            raise click.ClickException("No token provided on stdin.")
    else:
        token = click.prompt("GitCode token", hide_input=True)
    save_config({"token": token})
    click.echo("Authentication saved.")
