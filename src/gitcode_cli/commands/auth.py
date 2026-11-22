from __future__ import annotations

import os
import sys

import click

from .. import config
from ..config import LEGACY, Accounts, edit_accounts, get_token, load_config, valid_login
from ..context import AppContext
from ..errors import APIError, NetworkError
from ..formatters import output_result
from ..helptext import GCSectionGroup, set_gc_help
from ..services import UserService
from ..utils import safe_echo


def _override(ctx: click.Context) -> tuple[str, str] | None:
    explicit = ctx.find_root().params.get("token")
    if explicit:
        return "--token", explicit
    env_token = os.environ.get("GC_TOKEN")
    return ("GC_TOKEN", env_token) if env_token else None


def _require_local(ctx: click.Context) -> None:
    override = _override(ctx)
    if override:
        raise click.ClickException(f"{override[0]} overrides saved accounts. Remove the override first.")


def _verified_login(token: str) -> str:
    # Use only the supplied credential, not the process default, for this lookup.
    client = AppContext(token=token, repo=None).client()
    try:
        user = UserService(client).current()
    except (APIError, NetworkError):
        # Upstream errors can contain credentials or untrusted response bodies.
        raise click.ClickException("Unable to verify authentication with GitCode.") from None
    finally:
        client.close()
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not valid_login(login) or token in login:
        raise click.ClickException("Unable to verify authentication with GitCode.")
    return login


def _status_rows(ctx: click.Context, only_active: bool) -> list[tuple[str, str | None, str, bool]]:
    override = _override(ctx)
    if override:
        return [(override[0], None, override[1], True)]
    accounts = Accounts.from_config(load_config())
    return [
        (str(config.CONFIG_PATH), name, accounts.tokens[name], name == accounts.active)
        for name in sorted(accounts.tokens, key=lambda key: (key != accounts.active, key))
        if not only_active or name == accounts.active
    ]


def _structured_auth_status(rows: list[tuple[str, str | None, str, bool]]) -> dict:
    entries = []
    for source, name, token, active in rows:
        saved_login = name if name is not None and name != LEGACY else ""
        entry = {"host": "gitcode.com", "active": active, "tokenSource": source, "login": saved_login}
        try:
            login = _verified_login(token)
            if saved_login and saved_login != login:
                raise click.ClickException("Saved account no longer matches the authenticated identity.")
        except click.ClickException as exc:
            entry.update(state="error", error=exc.message)
        else:
            entry.update(state="success", login=login)
        entries.append(entry)
    return {"hosts": {"gitcode.com": entries} if entries else {}}


@click.group("auth", cls=GCSectionGroup, help="Authenticate gc with GitCode.")
def auth_group() -> None:
    pass


@auth_group.command("login", short_help="Authenticate with a GitCode token", help="Authenticate with a GitCode token.")
@click.option("--with-token", is_flag=True, help="Read token from stdin.")
@click.option("--account", is_flag=True, help="Verify this token and save it under its GitCode login.")
@click.pass_context
def auth_login(ctx: click.Context, with_token: bool, account: bool) -> None:
    if with_token:
        token = sys.stdin.read().strip()
        if not token:
            raise click.ClickException("No token provided on stdin.")
    else:
        token = click.prompt("GitCode token", hide_input=True).strip()
    if not token or any(c.isspace() for c in token):
        raise click.ClickException("Expected one non-empty token.")
    name = _verified_login(token) if account else LEGACY
    with edit_accounts() as accounts:
        accounts.tokens[name] = token
        accounts.active = name
    safe_echo(f"Authentication saved for {name}." if account else "Authentication saved.")
    override = _override(ctx)
    if override:
        safe_echo(f"Note: {override[0]} still overrides saved accounts.", err=True)


@auth_group.command("switch", short_help="Select a saved account", help="Select a saved GitCode account.")
@click.option("-u", "--user", help="Select this verified login.")
@click.option("--legacy", is_flag=True, help="Select the saved unnamed token.")
@click.pass_context
def auth_switch(ctx: click.Context, user: str | None, legacy: bool) -> None:
    if (user is None and not legacy) or (user is not None and legacy):
        raise click.UsageError("Specify exactly one of --user LOGIN or --legacy.")
    _require_local(ctx)
    name = LEGACY if legacy else user
    with edit_accounts() as accounts:
        accounts.require(name)
        accounts.active = name
    safe_echo(f"Switched to {name}.")


@auth_group.command(
    "logout", short_help="Remove saved authentication", help="Remove a locally saved token; does not revoke it."
)
@click.option("-u", "--user", help="Remove this saved login instead of the active account.")
@click.pass_context
def auth_logout(ctx: click.Context, user: str | None) -> None:
    _require_local(ctx)
    with edit_accounts() as accounts:
        if not accounts.tokens:
            raise click.ClickException("Not logged in.")
        name = user if user is not None else accounts.active
        accounts.require(name)
        assert name is not None
        del accounts.tokens[name]
        if accounts.active == name:
            accounts.active = None
    safe_echo("Logged out.")


@auth_group.command("status", short_help="Show authentication status", help="Show authentication status.")
@click.option("-a", "--active", is_flag=True, help="Show only the effective account.")
@click.option(
    "--json", "json_fields", is_flag=False, flag_value="", default=None, help="Output JSON; available field: hosts."
)
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression. Requires --json.")
@click.option("-t", "--template", help="Format JSON using a Go template string. Requires --json.")
@click.pass_context
def auth_status(
    ctx: click.Context, active: bool, json_fields: str | None, jq_query: str | None, template: str | None
) -> None:
    if jq_query is not None and template is not None:
        raise click.UsageError("Specify only one of --jq or --template.")
    if json_fields is None and (jq_query is not None or template is not None):
        raise click.UsageError("--jq and --template require --json.")
    if json_fields is not None and json_fields.strip() != "hosts":
        raise click.UsageError("Available JSON fields:\n  hosts")
    rows = _status_rows(ctx, active)
    if json_fields is not None:
        output_result(_structured_auth_status(rows), "hosts", jq_query, template, default_formatter=lambda _: None)
        return
    safe_echo("gitcode.com")
    effective = any(is_active for _, _, _, is_active in rows)
    if not effective:
        safe_echo("  X Not logged in to GitCode")
        safe_echo("  - Use `gc auth switch --user LOGIN`, run `gc auth login` or set GC_TOKEN.")
    for source, name, _, is_active in rows:
        label = f" ({name})" if name is not None and name != LEGACY else ""
        safe_echo(f"  ✓ Logged in to GitCode{label}" if is_active else f"  - Saved account: {name}")
        safe_echo(f"  - Active account: {str(is_active).lower()}")
        safe_echo(f"  - Token source: {source}")
    if rows:
        safe_echo("  - API host: https://api.gitcode.com")
    if os.environ.get("GC_GH_PROXY_ACTIVE") == "1":
        safe_echo("  - gh proxy: active; commands target GitCode, not GitHub")
        if not effective:
            raise click.exceptions.Exit(1)


set_gc_help(
    auth_status,
    gc_json_fields=["hosts"],
    gc_arguments_help=[
        "JSON output verifies listed accounts via GitCode and never includes tokens. "
        "Unavailable scopes and Git protocol are omitted. Authentication failures are reported "
        "in hosts with exit code 0; malformed configuration and output errors still fail."
    ],
    gc_examples=["gc auth status", "gc auth status --json hosts", "gc auth status --json hosts --jq '.hosts'"],
)


@auth_group.command("token", short_help="Print the active token", help="Print the active token.")
@click.option("-u", "--user", help="Print only this saved account's token (no fallback).")
@click.pass_context
def auth_token(ctx: click.Context, user: str | None) -> None:
    if user is not None:
        _require_local(ctx)
        token = Accounts.from_config(load_config()).require(user)
    else:
        token = get_token(ctx.find_root().params.get("token"))
    safe_echo(token)
