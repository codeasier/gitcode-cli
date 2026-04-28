from __future__ import annotations

import json
import re
import shutil
import subprocess

import click

from .utils import safe_echo


def dump_json(data, fields: list[str] | None = None) -> str:
    if fields:
        if isinstance(data, list):
            data = [_filter_fields(item, fields) for item in data]
        else:
            data = _filter_fields(data, fields)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _filter_fields(item: dict, fields: list[str]) -> dict:
    result = {}
    for field in fields:
        if "." in field:
            parts = field.split(".")
            value = item
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
            result[field] = value
        else:
            result[field] = item.get(field)
    return result


def _login_from(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            login = value.get("login") or value.get("username") or value.get("name")
            if login:
                return str(login)
        elif value:
            return str(value)
    return ""


def _list_row(item: dict, *, author_keys: tuple[str, ...]) -> str:
    return "\t".join(
        [
            f"#{item.get('number', '')}",
            str(item.get("state") or ""),
            str(item.get("title") or ""),
            _login_from(item, *author_keys),
        ]
    )


def format_issue_list(items: list[dict]) -> str:
    return "\n".join(_list_row(item, author_keys=("author", "user", "creator")) for item in items)


def format_pr_list(items: list[dict]) -> str:
    return "\n".join(_list_row(item, author_keys=("user", "author", "creator")) for item in items)


def _format_detail(item: dict, *, author_keys: tuple[str, ...], branch: str | None = None) -> str:
    number = item.get("number", "")
    title = item.get("title") or ""
    lines = [f"#{number} {title}", "", f"Title:\t{title}"]

    state = item.get("state")
    if state:
        lines.append(f"State:\t{state}")

    author = _login_from(item, *author_keys)
    if author:
        lines.append(f"Author:\t{author}")

    if branch:
        lines.append(f"Branch:\t{branch}")

    body = item.get("body") or ""
    lines.extend(["", "Body:", body])
    return "\n".join(lines)


def format_issue_detail(item: dict) -> str:
    return _format_detail(item, author_keys=("author", "user", "creator"))


def _branch_label(value) -> str:
    if isinstance(value, dict):
        label = value.get("label") or value.get("ref")
        return str(label) if label else ""
    return str(value) if value else ""


def format_pr_detail(item: dict) -> str:
    head = _branch_label(item.get("head"))
    base = _branch_label(item.get("base"))
    branch = f"{head} -> {base}" if head and base else None
    return _format_detail(item, author_keys=("user", "author", "creator"), branch=branch)


def apply_jq(data, query: str):
    try:
        import jq  # noqa: PLC0415

        return jq.compile(query).input(data).all()
    except ImportError:
        pass
    jq_bin = shutil.which("jq")
    if jq_bin:
        proc = subprocess.run(
            [jq_bin, query],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout)
    raise click.ClickException("jq is required for --jq. Install with: pip install pyjq or install jq CLI.")


def render_template(data, template: str) -> str:
    def replacer(match):
        key = match.group(1)
        if "." in key:
            parts = key.split(".")
            value = data
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
        else:
            value = data.get(key) if isinstance(data, dict) else None
        return str(value) if value is not None else ""

    return re.sub(r"\{\{\.(\w+(?:\.\w+)*)\}\}", replacer, template)


def output_result(data, json_fields: str | None, jq_query: str | None, template: str | None, default_formatter):
    if jq_query:
        data = apply_jq(data, jq_query)
        safe_echo(dump_json(data))
        return
    if json_fields:
        fields = [f.strip() for f in json_fields.split(",")]
        safe_echo(dump_json(data, fields=fields))
        return
    if template:
        if isinstance(data, list):
            for item in data:
                safe_echo(render_template(item, template))
        else:
            safe_echo(render_template(data, template))
        return
    default_formatter(data)
