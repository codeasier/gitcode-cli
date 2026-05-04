from __future__ import annotations

import contextlib
import importlib.metadata
import sys

import click
from click.shell_completion import get_completion_class

from . import __version__
from .commands.auth import auth_group
from .commands.issue import issue_group
from .commands.pr import pr_group
from .config import get_token
from .context import AppContext
from .errors import GCError
from .helptext import GCSectionGroup, set_gc_help
from .utils import safe_echo


def _configure_stdout_encoding() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and stream.isatty():
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def _get_version() -> str:
    try:
        return importlib.metadata.version("pygitcode")
    except importlib.metadata.PackageNotFoundError:
        return __version__


class _GCMainGroup(GCSectionGroup):
    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except GCError as exc:
            safe_echo(f"error: {exc}", err=True)
            ctx.exit(1)


@click.group(
    cls=_GCMainGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Work seamlessly with GitCode from the command line.",
)
@click.version_option(version=_get_version(), prog_name="gitcode")
@click.option("--repo", "repo_name", "-R", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.option("--token", hidden=True, help="Override authentication token.")
@click.pass_context
def main(ctx: click.Context, repo_name: str | None, token: str | None) -> None:
    _configure_stdout_encoding()
    ctx.ensure_object(dict)
    try:
        resolved_token = token or get_token()
    except GCError:
        resolved_token = token
    ctx.obj["app"] = AppContext(token=resolved_token or "", repo=repo_name)


set_gc_help(
    main,
    gc_usage="gc <command> <subcommand> [flags]",
    gc_command_sections=[
        ("CORE COMMANDS", ["auth", "issue", "pr"]),
        ("ADDITIONAL COMMANDS", ["completion", "version"]),
    ],
    gc_examples=[
        "gc issue create",
        "gc pr list -R owner/repo",
        "gc auth login",
    ],
    gc_learn_more=[
        "Use `gc <command> <subcommand> --help` for more information about a command.",
    ],
)


auth_group.short_help = "Authenticate gc with GitCode"
issue_group.short_help = "Manage issues"
pr_group.short_help = "Manage pull requests"


@main.command("version", short_help="Show gc version", help="Show gc version.")
def version_command() -> None:
    safe_echo(f"gitcode version {_get_version()}")


@main.command("completion", short_help="Generate shell completion scripts", help="Generate shell completion scripts.")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion_command(shell: str) -> None:
    comp_class = get_completion_class(shell)
    if comp_class is None:
        raise click.ClickException(f"Shell completion not supported for: {shell}")
    comp = comp_class(main, {}, "gc", "_GC_COMPLETE")
    safe_echo(comp.source())


main.add_command(auth_group)
main.add_command(issue_group)
main.add_command(pr_group)


if __name__ == "__main__":  # pragma: no cover
    main()
