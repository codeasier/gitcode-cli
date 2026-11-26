"""GitHub-style release workflows on GitCode's documented v5 API."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryFile
from typing import BinaryIO, cast
from urllib.parse import quote, urlsplit

import click

from .. import release_assets as binary
from .. import release_files as local
from .. import repo_read
from ..errors import GCError
from ..formatters import output_result
from ..helptext import GCSectionGroup, set_gc_help
from ..repo import is_single_ref, resolve_repo
from ..services.releases import ReleaseService, release_record, tag_segment
from ..utils import open_in_browser, safe_echo

repo_option = click.option("-R", "--repo", "repo_name", help="Select [HOST/]OWNER/REPO.")
title_option = click.option("-t", "--title", help="Release name.")
notes_option = click.option("-n", "--notes", help="Release description.")
file_option = click.option(
    "-F", "--notes-file", type=click.File("r", encoding="utf-8"), help="Read notes; '-' uses stdin."
)
pre_option = click.option("-p", "--prerelease", is_flag=True, help="Mark as a prerelease.")
latest_option = click.option("--latest", is_flag=True, help="Set GitCode's latest release status.")
json_option = click.option("--json", "fields", help="Comma-separated fields.")
jq_option = click.option("-q", "--jq", help="Filter JSON output with jq.")
template_option = click.option("--template", "-t", help="Format JSON output using a template.")
FIELDS = [
    "assets",
    "author",
    "body",
    "createdAt",
    "isLatest",
    "isPrerelease",
    "name",
    "tagName",
    "targetCommitish",
    "url",
]
_ARCHIVE_FIELDS = {"tarballUrl": "tar.gz", "zipballUrl": "zip"}
VIEW_FIELDS = [*FIELDS, *_ARCHIVE_FIELDS]
_ARCHIVE_SEGMENT = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}"
_ARCHIVE_REPO = re.compile(rf"https://gitcode\.com/{_ARCHIVE_SEGMENT}/({_ARCHIVE_SEGMENT})")


@contextmanager
def _service(ctx, repo_name):
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    client = app.client()
    try:
        yield ReleaseService(client, owner, repo), f"https://gitcode.com/{quote(owner, safe='')}/{quote(repo, safe='')}"
    finally:
        client.close()


def _web(base: str, row: dict) -> str | None:
    # The v5 schema need not include a release page. Never invent a per-tag URL.
    value = row.get("html_url")
    if not isinstance(value, str) or not value.startswith((base + "/releases/", base + "/-/releases/")):
        return None
    if urlsplit(value).query or urlsplit(value).fragment or any(c.isspace() or c == "\\" for c in value):
        return None
    if any(part in (".", "..") for part in urlsplit(value).path.split("/")):
        return None
    return value


def _project(row: dict, base: str, *, with_assets: bool = True) -> dict:
    status = row.get("release_status")
    author = row.get("author")
    return {
        "tagName": row["tag_name"],
        "name": row.get("name"),
        "body": row.get("body"),
        "author": {"login": author.get("login")} if isinstance(author, dict) else None,
        "createdAt": row.get("created_at"),
        "isLatest": True if status in ("latest", "lasted") else (False if status == "pre" else None),
        "isPrerelease": row.get("prerelease"),
        "targetCommitish": row.get("target_commitish"),
        "url": _web(base, row),
        # Never render temporary transfer URLs, callback headers or query credentials.
        "assets": [
            {k: a[k] for k in ("id", "name", "size", "digest") if k in a}
            for a in binary.asset_map(row).values()
            if not binary.is_archive(a)
        ]
        if with_assets and isinstance(row.get("assets"), list)
        else None,
    }


def _source_archive_urls(row: dict, base: str, fields: set[str], token: str) -> dict[str, str | None]:
    result: dict[str, str | None] = dict.fromkeys(fields)
    identity = _ARCHIVE_REPO.fullmatch(base)
    tag, assets = row["tag_name"], row.get("assets")
    if identity is None or not re.fullmatch(_ARCHIVE_SEGMENT, tag) or not is_single_ref(tag):
        return result
    if not isinstance(assets, list):
        return result
    for field in fields:
        suffix = _ARCHIVE_FIELDS[field]
        name = f"{identity[1]}-{tag}.{suffix}"
        key = binary.filename_key(name)
        matches = [
            a
            for a in assets
            if isinstance(a, dict) and isinstance(a.get("name"), str) and binary.filename_key(a["name"]) == key
        ]
        if len(matches) != 1:
            continue
        asset = matches[0]
        # Accept only the documented, unambiguous source route for this release.
        # Exact equality excludes URL aliases, encoded components and signed
        # query strings. The constructed URL is not used as a fallback.
        expected = f"{base}/-/archive/{tag}/{name}"
        url = asset.get("browser_download_url")
        if (
            asset["name"] == name
            and asset.get("type") in (None, "SOURCE", suffix)
            and isinstance(url, str)
            and url == expected
            and (not token or token not in url)
        ):
            result[field] = url
    return result


def _check_fields(fields: str | None, allowed: list[str] = FIELDS) -> set[str]:
    selected = {s.strip() for s in fields.split(",")} if fields else set()
    if selected.difference(allowed):
        raise click.UsageError("Available JSON fields: " + ", ".join(allowed))
    return selected


@click.group("release", cls=GCSectionGroup, help="Manage GitCode releases and release attachments.")
def release_group() -> None:
    pass


@release_group.command(
    "check-digest", help="Compare a local file to an uploaded attachment’s SHA-256 (not a signature)."
)
@click.argument("tag")
@click.argument("file", type=click.Path(path_type=Path))
@repo_option
@click.pass_context
def release_check_digest(ctx, tag: str, file: Path, repo_name: str | None) -> None:
    app = ctx.obj["app"]
    explicit = repo_name if repo_name is not None else app.repo
    if not explicit:
        raise click.UsageError("Use -R OWNER/REPO to select the repository explicitly.")
    owner, repo = resolve_repo(explicit)
    if repo_name is not None and app.repo is not None and (not app.repo or resolve_repo(app.repo) != (owner, repo)):
        raise click.UsageError("The command and global --repo values disagree.")
    repo_read.validate_target(owner, repo, tag)
    name = binary.safe_name(file.name)
    endpoint = f"/repos/{owner}/{repo}/releases/tags/{tag_segment(tag)}"
    data = repo_read.bounded_json("Release metadata", endpoint, {}, app.token, (owner, repo, tag))
    size, digest = binary.named_checksum(release_record(data, tag), name, owner=owner, repo=repo, tag=tag)
    local.check_local_digest(file, size, digest)
    safe_echo("SHA-256 matches GitCode attachment metadata. This is not a publisher signature.")


@release_group.command("list", help="List releases in API order (descending by default).")
@repo_option
@click.option("-L", "--limit", type=click.IntRange(min=1, max=10000), default=30, show_default=True)
@click.option("-O", "--order", type=click.Choice(["asc", "desc"]), default="desc")
@click.option("--exclude-pre-releases", is_flag=True)
@json_option
@jq_option
@template_option
@click.pass_context
def release_list(ctx, repo_name, limit, order, exclude_pre_releases, fields, jq, template):
    _check_fields(fields)
    with _service(ctx, repo_name) as (svc, base):
        rows = [_project(r, base) for r in svc.list(limit, order, exclude_pre_releases)]
    output_result(
        rows, fields, jq, template, lambda data: [safe_echo(f"{r['tagName']}\t{r['name'] or ''}") for r in data]
    )


@release_group.command("view", help="Show a release by tag; with no tag use GitCode's latest selector.")
@click.argument("tag", required=False)
@repo_option
@click.option("-w", "--web", is_flag=True)
@json_option
@jq_option
@template_option
@click.pass_context
def release_view(ctx, tag, repo_name, web, fields, jq, template):
    selected = _check_fields(fields, VIEW_FIELDS)
    archive_fields = selected.intersection(_ARCHIVE_FIELDS)
    if web and (fields or jq or template):
        raise click.UsageError("--web cannot be combined with output formatting")
    with _service(ctx, repo_name) as (svc, base):
        raw = svc.get(tag)
        row = _project(raw, base, with_assets=not archive_fields or "assets" in selected)
        if archive_fields:
            row.update(_source_archive_urls(raw, base, archive_fields, ctx.obj["app"].token))
    if web:
        if not row["url"]:
            safe_echo("No individual release page returned; opening the repository releases list.", err=True)
        open_in_browser(row["url"] or base + "/releases")
    else:
        output_result(
            row,
            fields,
            jq,
            template,
            lambda r: safe_echo(f"{r['name'] or r['tagName']}\n{r['body'] or ''}\n{r['url'] or ''}"),
        )


def _changes(title, notes, notes_file, prerelease, latest) -> dict:
    if prerelease and latest:
        raise click.UsageError("--prerelease and --latest are mutually exclusive on GitCode")
    if notes is not None and notes_file is not None:
        raise click.UsageError("--notes and --notes-file are mutually exclusive")
    data = {}
    if title is not None:
        data["name"] = title
    if notes is not None or notes_file is not None:
        try:
            data["body"] = notes if notes is not None else notes_file.read()
        except (UnicodeError, OSError):
            raise click.ClickException("Unable to read release notes as UTF-8.") from None
    if prerelease or latest:
        data["release_status"] = "pre" if prerelease else "latest"
    return data


def _attachment_id(item) -> int:
    if not item or binary.is_archive(item) or type(item.get("id")) is not int or item["id"] < 1:
        raise GCError("No unambiguous uploaded asset ID for this name.")
    return item["id"]


def _remove(svc, tag, name, ident):
    svc.delete_asset(tag, ident)
    if name in binary.asset_map(svc.get(tag)):
        raise GCError("Asset removal not confirmed; inspect the release before retrying.")


def _upload_all(svc, release, paths, clobber=False):
    tag = release["tag_name"]
    current = {binary.filename_key(name): row for name, row in binary.asset_map(release).items()}
    existing = {}
    for item in paths:
        row = current.get(binary.filename_key(item.name))
        if row is not None:
            if row["name"] != item.name:
                raise GCError("Upload filename collides with an existing asset after normalization.")
            if not clobber:
                raise GCError("An asset already has this name; use --clobber to delete and re-upload it.")
            existing[item.name] = _attachment_id(row)
    for item in paths:
        if item.name in existing:
            # No API for an atomic replacement. Delete the observed ID, never a tag or archive.
            _remove(svc, tag, item.name, existing[item.name])
            safe_echo(f"Deleted old asset {item.name}; replacement is not yet uploaded.", err=True)
        ticket = svc.ticket(tag, item.name)
        binary.reject_reflected_credential(ticket.get("url"), svc.client.token)
        if isinstance(ticket.get("headers"), dict):
            for value in ticket["headers"].values():
                binary.reject_reflected_credential(value, svc.client.token)
        sent = binary.upload(item.stream, item.size, ticket)
        # A successful object-store PUT alone does not prove callback registration.
        registered = binary.asset_map(svc.get(tag)).get(item.name)
        if registered is None:
            raise GCError("Upload accepted but asset registration is not confirmed; inspect before retrying.")
        binary.check_registration(registered, sent)
        safe_echo(f"Uploaded {item.name}", err=True)


@release_group.command(
    "create", help="Publish a release. GitCode can create a missing tag; use --verify-tag to require an existing tag."
)
@click.argument("tag")
@click.argument("files", nargs=-1, type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path))
@repo_option
@title_option
@notes_option
@file_option
@pre_option
@latest_option
@click.option("--target", help="Branch or commit for a missing tag.")
@click.option("--verify-tag", is_flag=True)
@click.pass_context
def release_create(ctx, tag, files, repo_name, title, notes, notes_file, prerelease, latest, target, verify_tag):
    data = _changes(title, notes, notes_file, prerelease, latest)
    data.setdefault("name", tag)
    data.setdefault("body", "")
    if target:
        data["target_commitish"] = target
    with local.uploads(files) as paths, _service(ctx, repo_name) as (svc, base):
        if verify_tag:
            svc.require_tag(tag)
        record = svc.create(tag, data)
        safe_echo(_web(base, record) or "Published release " + record["tag_name"])
        if paths:
            # No rollback: users must know when the release itself was created.
            _upload_all(svc, record, paths)


@release_group.command("edit", help="Edit title, notes or GitCode release status without changing the tag.")
@click.argument("tag")
@repo_option
@title_option
@notes_option
@file_option
@pre_option
@latest_option
@click.pass_context
def release_edit(ctx, tag, repo_name, title, notes, notes_file, prerelease, latest):
    changes = _changes(title, notes, notes_file, prerelease, latest)
    if not changes:
        raise click.UsageError("Specify a title, notes or release status to edit.")
    with _service(ctx, repo_name) as (svc, base):
        existing = svc.get(tag)
        for key in ("name", "body"):
            if key not in changes:
                if not isinstance(existing.get(key), str):
                    raise GCError("Incomplete release metadata; refusing to overwrite a missing field.")
                changes[key] = existing[key]
        updated = svc.edit(tag, changes)
        safe_echo(_web(base, updated) or "Updated release " + updated["tag_name"])


@release_group.command("upload", help="Upload files to an existing release (POSIX).")
@click.argument("tag")
@click.argument(
    "files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path)
)
@repo_option
@click.option(
    "--clobber", is_flag=True, help="Delete existing assets before uploading; a failure may lose the old file."
)
@click.pass_context
def release_upload(ctx, tag, files, repo_name, clobber):
    with local.uploads(files) as paths, _service(ctx, repo_name) as (svc, _):
        _upload_all(svc, svc.get(tag), paths, clobber)


@release_group.command("delete-asset", help="Remove one release attachment by exact name (never deletes its tag).")
@click.argument("tag")
@click.argument("asset_name")
@repo_option
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation.")
@click.pass_context
def release_delete_asset(ctx, tag, asset_name, repo_name, yes):
    with _service(ctx, repo_name) as (svc, _):
        item = binary.asset_map(svc.get(tag)).get(binary.safe_name(asset_name))
        ident = _attachment_id(item)
        if not yes:
            click.confirm(f"Delete {asset_name} from release {tag}?", abort=True)
        _remove(svc, tag, asset_name, ident)


def _download_files(rows, directory, output, clobber, skip_existing, *, secret: str):
    if output is not None and len(rows) != 1:
        raise click.UsageError("--output requires exactly one matching asset.")
    try:
        if output == "-":
            # Click 8.5 exposes this helper via dynamic attribute lookup.
            get_binary_stream = getattr(click, "get_binary_stream", None)
            if not callable(get_binary_stream):
                raise GCError("Cannot verify a binary stdout stream; use --output FILE instead.")
            unsafe_stdout = "Refusing to write binary release data to a terminal; redirect stdout."
            try:
                stream = cast(Callable[[str], BinaryIO], get_binary_stream)("stdout")
                isatty = getattr(stream, "isatty", None)
                can_write = callable(getattr(stream, "write", None))
                is_redirected = callable(isatty) and isatty() is False and can_write
            except (AttributeError, OSError, RuntimeError, TypeError):
                raise GCError(unsafe_stdout) from None
            if not is_redirected:
                raise GCError(unsafe_stdout)
            with TemporaryFile() as temp:
                binary.download(rows[0], temp, secret=secret)
                temp.seek(0)
                shutil.copyfileobj(temp, stream)
            return
        path = Path(output).parent if output else directory
        names = [binary.safe_name(Path(output).name if output else row["name"]) for row in rows]
        with local.directory(path, create=True, writable=True) as parent:
            pairs = []
            for row, name in zip(rows, names):
                present = local.exists(parent, name)
                if present and not (skip_existing or clobber):
                    raise GCError("Destination already exists; use --skip-existing or --clobber.")
                if not (present and skip_existing):
                    pairs.append((row, name))
            for row, name in pairs:
                local.save(row, path, parent, name, clobber=clobber, secret=secret)
                safe_echo(f"Downloaded {path / name}", err=True)
    except OSError:
        raise GCError("Unable to install release asset; existing completed files were preserved.") from None


@release_group.command(
    "download", help="Download attachments to files on POSIX or to redirected stdout; use --archive for source code."
)
@click.argument("tag", required=False)
@repo_option
@click.option("-p", "--pattern", multiple=True, help="Match attachment names (repeatable).")
@click.option("-A", "--archive", type=click.Choice(["zip", "tar.gz"]))
@click.option("-D", "--dir", "directory", type=click.Path(file_okay=False, path_type=Path), default=".")
@click.option("-O", "--output", help="Write a single asset to this file, or '-' for stdout.")
@click.option("--clobber", is_flag=True)
@click.option("--skip-existing", is_flag=True)
@click.pass_context
def release_download(ctx, tag, repo_name, pattern, archive, directory, output, clobber, skip_existing):
    if not tag and not (pattern or archive):
        raise click.UsageError("Latest release requires --pattern or --archive.")
    if (pattern and archive) or (clobber and skip_existing) or (output and directory != Path(".")):
        raise click.UsageError("Conflicting download options.")
    with _service(ctx, repo_name) as (svc, _):
        record = svc.get(tag)
        selected = binary.select_assets(record, pattern, archive)
        temporary = binary.asset_map(svc.download_metadata(record["tag_name"]))
        checked = []
        secret = svc.client.token
        for row in selected:
            item = temporary.get(row["name"])
            if (
                not item
                or binary.is_archive(item) != binary.is_archive(row)
                or (
                    row.get("id") is not None
                    and (type(item.get("id")) is not type(row["id"]) or item.get("id") != row["id"])
                )
                or any(row.get(k) is not None and item.get(k) not in (None, row[k]) for k in ("size", "digest"))
            ):
                raise GCError("Release assets changed; retry with fresh metadata.")
            integrity = {k: item[k] for k in ("size", "digest") if item.get(k) is not None}
            transfer_url = item.get("temp_download_url") or item.get("browser_download_url")
            binary.reject_reflected_credential(transfer_url, secret)
            checked.append({**row, **integrity, "browser_download_url": binary.asset_url(transfer_url)})
    _download_files(checked, directory, output, clobber, skip_existing, secret=secret)


release_group.add_command(release_list, name="ls")
release_group.add_command(release_create, name="new")
set_gc_help(
    release_group,
    gc_usage="gc release <command> [flags]",
    gc_command_sections=[
        ("GENERAL COMMANDS", ["create", "list"]),
        ("TARGETED COMMANDS", ["check-digest", "delete-asset", "download", "edit", "upload", "view"]),
    ],
    gc_examples=[
        "gc release view -R owner/repo",
        "gc release download v1.2.3 -p '*.whl'",
    ],
)
set_gc_help(release_create, gc_aliases=["new"])
set_gc_help(release_list, gc_json_fields=FIELDS, gc_aliases=["ls"])
set_gc_help(release_view, gc_json_fields=VIEW_FIELDS)
