"""Structured output for bounded result lists with declared projection fields."""

from __future__ import annotations

import click

from ..formatters import output_result


def listing_options(f):
    f = click.option("--template", "-t", help="Format the selected JSON fields as a template.")(f)
    f = click.option("--jq", "-q", "jq_query", help="Filter the selected JSON fields with jq.")(f)
    return click.option("--json", "json_fields", metavar="FIELDS", help="Output comma-separated JSON fields.")(f)


def selected_fields(raw, available, jq_query, template):
    if (jq_query or template) and not raw:
        raise click.UsageError("--jq and --template require --json FIELDS.")
    if jq_query and template:
        raise click.UsageError("Use only one of --jq or --template.")
    if raw is None:
        return None
    fields = [field.strip() for field in raw.split(",")]
    if not all(field in available for field in fields):
        raise click.UsageError("Available JSON fields: " + ", ".join(available))
    return fields


def render_listing(rows, fields, jq_query, template, formatter):
    if fields is None:
        formatter(rows)
    else:
        data = [{field: row.get(field) for field in fields} for row in rows]
        output_result(data, ",".join(fields), jq_query, template, formatter)
