from __future__ import annotations

import click

from ..config import get_token, load_config, save_config
from ..helptext import GCSectionGroup
from ..utils import safe_echo


@click.group("auth", cls=GCSectionGroup, help="Authenticate gc with GitCode.")
def auth_group() -> None:
    pass


@auth_group.command("login", short_help="Authenticate with a GitCode token", help="Authenticate with a GitCode token.")
@click.option("--with-token", is_flag=True, help="Read token from stdin.")
def auth_login(with_token: bool) -> None:
    if with_token:
        token = click.get_text_stream("stdin").read().strip()
        if not token:
            raise click.ClickException("No token provided on stdin.")
    else:
        token = click.prompt("GitCode token", hide_input=True)
    save_config({"token": token})
    safe_echo("Authentication saved.")


@auth_group.command("logout", short_help="Remove saved authentication", help="Remove saved authentication.")
def auth_logout() -> None:
    config = load_config()
    if "token" not in config:
        raise click.ClickException("Not logged in.")
    del config["token"]
    save_config(config)
    safe_echo("Logged out.")


@auth_group.command("status", short_help="Show authentication status", help="Show authentication status.")
def auth_status() -> None:
    try:
        token = get_token()
    except Exception:
        safe_echo("Not logged in. Run `gc auth login` to authenticate.")
        return
    masked = token[:4] + "****" if len(token) > 4 else "****"
    safe_echo(f"Logged in to GitCode (token: {masked})")


@auth_group.command("token", short_help="Print the active token", help="Print the active token.")
def auth_token() -> None:
    try:
        token = get_token()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    safe_echo(token)
