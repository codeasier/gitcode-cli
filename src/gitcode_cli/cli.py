from __future__ import annotations

import click

from . import __version__
from .commands.auth import auth_group
from .commands.issue import issue_group
from .commands.pr import pr_group
from .config import get_token
from .context import AppContext
from .errors import GCError


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="gc")
@click.option("--repo", "repo_name", "-R", help="Repository in OWNER/REPO format (default: gitcode.com).")
@click.option("--token", hidden=True, help="Override authentication token.")
@click.pass_context
def main(ctx: click.Context, repo_name: str | None, token: str | None) -> None:
    ctx.ensure_object(dict)
    try:
        resolved_token = token or get_token()
    except GCError:
        resolved_token = token
    ctx.obj["app"] = AppContext(token=resolved_token or "", repo=repo_name)


@main.result_callback()
def process_result(*_args: object, **_kwargs: object) -> None:
    return None


@main.command("version")
def version_command() -> None:
    click.echo(f"gc version {__version__}")


main.add_command(auth_group)
main.add_command(issue_group)
main.add_command(pr_group)


if __name__ == "__main__":  # pragma: no cover
    main()
