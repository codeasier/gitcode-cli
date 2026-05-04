from __future__ import annotations

import textwrap
from typing import Any

import click

LEARN_MORE_LINES = [
    "Use `gc <command> <subcommand> --help` for more information about a command.",
]


class GCSectionCommand(click.Command):
    def get_help(self, ctx: click.Context) -> str:
        return _render_help(self, ctx)


class GCSectionGroup(click.Group):
    command_class = GCSectionCommand

    def get_help(self, ctx: click.Context) -> str:
        return _render_help(self, ctx)


def set_gc_help(command: click.Command, **metadata: Any) -> None:
    for key, value in metadata.items():
        setattr(command, key, value)


def _render_help(command: click.Command, ctx: click.Context) -> str:
    sections: list[str] = []
    help_text = _clean_text(command.help)
    if help_text:
        sections.append(help_text)

    sections.append("USAGE\n  " + _usage_line(command, ctx))

    if isinstance(command, click.Group):
        command_sections = _command_sections(command)
        for title, section_rows in command_sections:
            if section_rows:
                sections.append(_definition_section(title, section_rows))
    else:
        aliases = getattr(command, "gc_aliases", [])
        if aliases:
            parent_path = _display_command_path(ctx).rsplit(" ", 1)[0]
            sections.append("ALIASES\n" + "\n".join(f"  {parent_path} {alias}" for alias in aliases))

    flag_rows = _flag_rows(command, ctx)
    inherited_flag_rows = _inherited_flag_rows(command, ctx)
    if flag_rows:
        sections.append(_definition_section("FLAGS", flag_rows))
    if inherited_flag_rows:
        sections.append(_definition_section("INHERITED FLAGS", inherited_flag_rows))

    argument_help = getattr(command, "gc_arguments_help", None)
    if argument_help:
        sections.append(_argument_section(argument_help))

    json_fields = getattr(command, "gc_json_fields", None)
    if json_fields:
        sections.append(_wrapped_list_section("JSON FIELDS", json_fields))

    examples = getattr(command, "gc_examples", None)
    if examples:
        sections.append("EXAMPLES\n" + "\n".join(f"  $ {example}" for example in examples))

    learn_more = getattr(command, "gc_learn_more", LEARN_MORE_LINES)
    if learn_more:
        sections.append("LEARN MORE\n" + "\n".join(f"  {line}" for line in learn_more))

    return "\n\n".join(section.rstrip() for section in sections if section).rstrip() + "\n"


def _usage_line(command: click.Command, ctx: click.Context) -> str:
    usage_suffix = getattr(command, "gc_usage", None)
    if usage_suffix:
        return usage_suffix

    pieces = [_display_command_path(ctx)]
    if isinstance(command, click.Group):
        pieces.append("<command>")
        if ctx.parent is None:
            pieces.append("<subcommand>")
    else:
        for param in command.get_params(ctx):
            if isinstance(param, click.Argument):
                pieces.append(param.make_metavar(ctx))
    if any(isinstance(param, click.Option) and not param.hidden for param in command.get_params(ctx)):
        pieces.append("[flags]")
    return " ".join(piece for piece in pieces if piece)


def _display_command_path(ctx: click.Context) -> str:
    parts = ctx.command_path.split()
    if not parts:
        return "gc"
    parts[0] = "gc"
    return " ".join(parts)


def _command_sections(command: click.Group) -> list[tuple[str, list[tuple[str, str]]]]:
    configured = getattr(command, "gc_command_sections", None)
    if configured:
        sections: list[tuple[str, list[tuple[str, str]]]] = []
        for title, names in configured:
            section_rows: list[tuple[str, str]] = []
            for name in names:
                subcommand = command.get_command(click.Context(command), name)
                if subcommand is None:
                    continue
                section_rows.append((f"{name}:", _command_summary(subcommand)))
            if section_rows:
                sections.append((title, section_rows))
        return sections

    seen: set[int] = set()
    rows: list[tuple[str, str]] = []
    for name in command.list_commands(click.Context(command)):
        subcommand = command.get_command(click.Context(command), name)
        if subcommand is None or id(subcommand) in seen:
            continue
        seen.add(id(subcommand))
        rows.append((f"{name}:", _command_summary(subcommand)))
    return [("COMMANDS", rows)] if rows else []


def _command_summary(command: click.Command) -> str:
    return command.short_help or _first_line(command.help) or ""


def _flag_rows(command: click.Command, ctx: click.Context) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    inherited_option_names = _inherited_option_names(ctx)
    for param in command.get_params(ctx):
        if not isinstance(param, click.Option) or param.hidden:
            continue
        if any(opt in inherited_option_names for opt in param.opts + param.secondary_opts):
            continue
        record = param.get_help_record(ctx)
        if record is None:
            continue
        rows.append(record)
    return rows


def _inherited_flag_rows(command: click.Command, ctx: click.Context) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if ctx.parent is None:
        return rows
    for param in ctx.parent.command.get_params(ctx.parent):
        if not isinstance(param, click.Option) or param.hidden:
            continue
        if "--help" in param.opts or "-h" in param.opts:
            continue
        if "--version" in param.opts:
            continue
        record = param.get_help_record(ctx.parent)
        if record is None:
            continue
        rows.append(record)
    if not rows or isinstance(command, click.Group):
        rows.append(("--help", "Show help for command"))
    return rows


def _inherited_option_names(ctx: click.Context) -> set[str]:
    if ctx.parent is None:
        return set()
    names: set[str] = set()
    for param in ctx.parent.command.get_params(ctx.parent):
        if not isinstance(param, click.Option) or param.hidden:
            continue
        names.update(param.opts)
        names.update(param.secondary_opts)
    return names


def _definition_section(title: str, rows: list[tuple[str, str]]) -> str:
    width = max(len(left) for left, _ in rows) + 2
    body = "\n".join(f"  {left.ljust(width)}{right}".rstrip() for left, right in rows)
    return f"{title}\n{body}"


def _argument_section(argument_help: str | list[str]) -> str:
    if isinstance(argument_help, str):
        body = "\n".join(f"  {line}" for line in argument_help.splitlines())
    else:
        body = "\n".join(f"  {line}" for line in argument_help)
    return f"ARGUMENTS\n{body}"


def _wrapped_list_section(title: str, values: list[str]) -> str:
    body = textwrap.fill(
        ", ".join(values),
        width=78,
        initial_indent="  ",
        subsequent_indent="  ",
    )
    return f"{title}\n{body}"


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return textwrap.dedent(value).strip()


def _first_line(value: str | None) -> str:
    text = _clean_text(value)
    return text.splitlines()[0] if text else ""
