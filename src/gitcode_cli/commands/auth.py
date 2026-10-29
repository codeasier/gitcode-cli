from __future__ import annotations

import os
import sys

import click

from .. import config
from ..config import get_token, load_config, save_config
from ..errors import APIError, NetworkError
from ..formatters import output_result
from ..helptext import GCSectionGroup, set_gc_help
from ..services import UserService
from ..utils import safe_echo


def _structured_auth_status(ctx: click.Context) -> dict:
    app = ctx.obj["app"]
    if not app.token:
        # A malformed config is a fatal error, rather than a logged-out account.
        load_config()
        return {"hosts": {}}
    if ctx.find_root().params.get("token"):
        token_source = "--token"
    elif os.environ.get("GC_TOKEN"):
        token_source = "GC_TOKEN"
    else:
        token_source = str(config.CONFIG_PATH)
    entry = {"host": "gitcode.com", "active": True, "tokenSource": token_source, "login": ""}
    try:
        user = UserService(app.client()).current()
        login = (user.get("login") or user.get("username")) if isinstance(user, dict) else None
        if not isinstance(login, str) or not login.strip():
            raise APIError("Current user response has no login")
    except (APIError, NetworkError):
        # Do not export raw API errors: upstream diagnostics can contain credentials.
        entry.update(state="error", error="Unable to verify authentication with GitCode.")
    else:
        entry.update(state="success", login=login)
    return {"hosts": {"gitcode.com": [entry]}}


@click.group("auth", cls=GCSectionGroup, help="Authenticate gc with GitCode.")
def auth_group() -> None:
    pass


@auth_group.command("login", short_help="Authenticate with a GitCode token", help="Authenticate with a GitCode token.")
@click.option("--with-token", is_flag=True, help="Read token from stdin.")
def auth_login(with_token: bool) -> None:
    if with_token:
        token = sys.stdin.read().strip()
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
@click.option(
    "--json", "json_fields", is_flag=False, flag_value="", default=None, help="Output JSON; available field: hosts."
)
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression. Requires --json.")
@click.option("-t", "--template", help="Format JSON using a Go template string. Requires --json.")
@click.pass_context
def auth_status(ctx: click.Context, json_fields: str | None, jq_query: str | None, template: str | None) -> None:
    if jq_query is not None and template is not None:
        raise click.UsageError("Specify only one of --jq or --template.")
    if json_fields is None and (jq_query is not None or template is not None):
        raise click.UsageError("--jq and --template require --json.")
    if json_fields is not None:
        if json_fields.strip() != "hosts":
            raise click.UsageError("Available JSON fields:\n  hosts")
        output_result(_structured_auth_status(ctx), "hosts", jq_query, template, default_formatter=lambda _: None)
        return
    try:
        token = get_token()
    except Exception:
        safe_echo("gitcode.com")
        safe_echo("  X Not logged in to GitCode")
        safe_echo("  - Run `gc auth login` or set GC_TOKEN to authenticate.")
        if os.environ.get("GC_GH_PROXY_ACTIVE") == "1":
            safe_echo("  - gh proxy: active; commands target GitCode, not GitHub")
            raise click.exceptions.Exit(1) from None
        return
    masked = token[:4] + "****" if len(token) > 4 else "****"
    safe_echo("gitcode.com")
    safe_echo("  ✓ Logged in to GitCode")
    safe_echo("  - Active account: true")
    safe_echo("  - API host: https://api.gitcode.com")
    safe_echo(f"  - Token: {masked}")
    if os.environ.get("GC_GH_PROXY_ACTIVE") == "1":
        safe_echo("  - gh proxy: active; commands target GitCode, not GitHub")


set_gc_help(
    auth_status,
    gc_json_fields=["hosts"],
    gc_arguments_help=[
        "JSON output verifies the current user for gitcode.com and never includes the token. "
        "Unavailable scopes and Git protocol are omitted. Authentication failures are reported "
        "in hosts with exit code 0; malformed configuration and output errors still fail."
    ],
    gc_examples=["gc auth status", "gc auth status --json hosts", "gc auth status --json hosts --jq '.hosts'"],
)


@auth_group.command("token", short_help="Print the active token", help="Print the active token.")
def auth_token() -> None:
    try:
        token = get_token()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    safe_echo(token)
