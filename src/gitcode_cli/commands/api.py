"""A bounded gh-style API escape hatch for the documented GitCode REST origin."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, BinaryIO

import click

from ..context import AppContext
from ..errors import APIError
from ..repo import parse_repo_with_host, resolve_repo
from ..repo_read import validate_target
from ..rest_api import (
    MAX_BYTES,
    READ_METHODS,
    Page,
    clean_response,
    fetch,
    is_v8_runs_pagination_endpoint,
    request_body,
    validate_field,
)
from ..utils import safe_echo


def _fields(raw_fields: tuple[str, ...], fields: tuple[str, ...]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for typed, specs in ((False, raw_fields), (True, fields)):
        for entry in specs:
            key, sep, value = entry.partition("=")
            validate_field(key)
            if not sep or key in values:
                raise click.UsageError("Supply each field once as key=value.")
            if typed and value.startswith("@"):
                raise click.UsageError("Use --input FILE for a JSON payload; typed @file fields are not supported.")
            if typed and re.fullmatch(r"true|false|null|-?(?:0|[1-9][0-9]*)", value):
                try:
                    values[key] = json.loads(value)
                except ValueError:
                    raise click.UsageError("Invalid typed field value.") from None
            else:
                values[key] = value
    return values


def _input(stream: BinaryIO | None) -> bytes | None:
    if stream is None:
        return None
    try:
        return stream.read(MAX_BYTES + 1)
    except OSError:
        raise click.UsageError("Unable to read the JSON request body.") from None


def _endpoint(raw: str, repo: str | None, *, pinned_scope: bool) -> tuple[str, tuple[str, str] | None]:
    placeholders = "{owner}" in raw or "{repo}" in raw
    if pinned_scope:
        if repo is None:
            if placeholders:
                raise click.UsageError("v8 run pagination placeholders require an explicit -R OWNER/REPO.")
            return raw, None
        host, owner, name = parse_repo_with_host(repo)
        if host not in {None, "gitcode.com"}:
            raise click.UsageError("v8 run pagination requires a canonical GitCode repository for -R.")
        validate_target(owner, name, None)
    elif repo or placeholders:
        owner, name = resolve_repo(repo)
    else:
        return raw, None
    if placeholders:
        raw = raw.replace("{owner}", owner).replace("{repo}", name)
    return raw, (owner, name)


def _jq(executable: str, query: str, data: Any) -> list[Any]:
    # A file for stdin avoids a pipe deadlock. Bound external jq output without
    # inheriting credentials (jq's env exposes all of its process variables).
    with tempfile.TemporaryFile() as source:
        source.write(json.dumps(data, allow_nan=False).encode())
        source.seek(0)
        with (
            subprocess.Popen(
                [executable, "-c", "--", query],
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={},
            ) as process,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            assert process.stdout is not None
            pending = pool.submit(process.stdout.read, MAX_BYTES + 1)
            try:
                raw = pending.result(timeout=15)
                if len(raw) > MAX_BYTES or process.wait(timeout=1) != 0:
                    raise ValueError("jq output exceeded limit or jq failed")
            finally:
                if process.poll() is None:
                    process.kill()
    # jq -c emits a stream of complete JSON values, one per line. In
    # particular a single array must remain one value, not become its elements.
    return [json.loads(line) for line in raw.split(b"\n") if line]


def _output_text(value: Any, filtered: bool) -> str:
    if filtered and isinstance(value, str) and (not value or value.isprintable()):
        return value
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    return re.sub(r"[\x7f-\x9f\ud800-\udfff]", lambda m: f"\\u{ord(m[0]):04x}", text)


def _format(
    pages: list[Page],
    include: bool,
    silent: bool,
    slurp: bool,
    jq: tuple[str, str] | None,
    token: str,
) -> str | None:
    if slurp:
        pages = [Page(pages[0].status, {}, [page.data for page in pages], True)]
    output = []
    remaining = MAX_BYTES
    for page in pages:
        block = []
        if include:
            block = [f"HTTP {page.status}", *(f"{k}: {v}" for k, v in page.headers.items()), ""]
        if page.has_body and not silent:
            values = _jq(*jq, page.data) if jq else [page.data]
            for value in values:
                printable = clean_response(value, token) if jq else value
                block.append(_output_text(printable, jq is not None))
        if block:
            text = "\n".join(block)
            remaining -= len(text.encode()) + 1
            if remaining < 0:
                raise ValueError("REST output exceeded limit")
            output.append(text)
    return "\n".join(output) if output else None


@click.command("api", short_help="Make a GitCode REST API request")
@click.argument("endpoint")
@click.option(
    "-X", "--method", type=click.Choice(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], case_sensitive=False)
)
@click.option("--api-version", type=click.Choice(["v5", "v8"]), help="Defaults to v5 unless the path specifies v8.")
@click.option("-f", "--raw-field", multiple=True, help="Flat string field, key=value (repeatable).")
@click.option("-F", "--field", multiple=True, help="Flat field; integers, true, false and null are typed.")
@click.option("-H", "--header", multiple=True, help="Accept or a conditional request header (Name: value).")
@click.option("--input", "input_stream", type=click.File("rb"), help="JSON body from a file, or '-' for stdin.")
@click.option(
    "--paginate", is_flag=True, help="Page GET arrays or the v8 runs listing; at most 100 requests, no partial output."
)
@click.option("--slurp", is_flag=True, help="Return all pages as one JSON array (requires --paginate).")
@click.option("-i", "--include", is_flag=True, help="Print the status and safe response headers before each body.")
@click.option("--silent", is_flag=True, help="Do not print response bodies.")
@click.option("-q", "--jq", help="Filter response JSON using jq.")
@click.pass_obj
def api_command(
    obj: dict,
    endpoint: str,
    method: str | None,
    api_version: str | None,
    raw_field: tuple[str, ...],
    field: tuple[str, ...],
    header: tuple[str, ...],
    input_stream: BinaryIO | None,
    paginate: bool,
    slurp: bool,
    include: bool,
    silent: bool,
    jq: str | None,
) -> None:
    """Request JSON from api.gitcode.com using a relative REST ENDPOINT (not a URL).

    Use e.g. 'repos/{owner}/{repo}/issues' or '/api/v8/repos/OWNER/REPO/actions/runs'.
    Fields or a body default the method to POST; use -X GET for query fields. With
    --input, fields become query parameters. Use gc -R OWNER/REPO api ... to
    override the origin used for {owner} and {repo}. GraphQL is not supported.
    """
    app: AppContext = obj["app"]
    method = (method or ("POST" if raw_field or field or input_stream is not None else "GET")).upper()
    if paginate and method != "GET":
        raise click.UsageError("--paginate is available only with GET (use -X GET with fields).")
    if slurp and (not paginate or include):
        raise click.UsageError("--slurp requires --paginate and cannot include HTTP headers.")
    if silent and jq:
        raise click.UsageError("Choose --silent or --jq.")
    if input_stream is not None and method in READ_METHODS:
        raise click.UsageError("GET and HEAD cannot carry a JSON request body.")
    values = _fields(raw_field, field)
    as_query = method in READ_METHODS or input_stream is not None
    query = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in values.items()} if as_query else {}
    body = request_body(_input(input_stream), {} if as_query else values, app.token)
    jq_command = None
    if jq:
        executable = shutil.which("jq")
        if executable is None:
            raise click.UsageError("--jq requires the jq executable on PATH.")
        jq_command = (executable, jq)
    pin_scope = paginate and is_v8_runs_pagination_endpoint(endpoint, api_version)
    resolved_endpoint, scope = _endpoint(endpoint, app.repo, pinned_scope=pin_scope)
    if paginate and not pin_scope and is_v8_runs_pagination_endpoint(resolved_endpoint, api_version):
        raise click.UsageError("v8 run pagination requires the literal actions/runs route.")
    pages = fetch(resolved_endpoint, api_version, method, app.token, header, query, body, paginate, repo_scope=scope)
    try:
        output = _format(pages, include, silent, slurp, jq_command, app.token)
    except (OSError, ValueError, RecursionError, FutureTimeout, subprocess.SubprocessError):
        # A jq diagnostic could echo a response or filter verbatim. An output failure
        # is not a failed write; never invite retrying a successful request.
        note = " The write request succeeded; do not repeat it." if method not in READ_METHODS else ""
        hint = " Check the jq expression or output size." if jq else " Check the output size."
        raise APIError("Unable to format the REST result." + hint + note) from None
    if output is not None:
        safe_echo(output)
