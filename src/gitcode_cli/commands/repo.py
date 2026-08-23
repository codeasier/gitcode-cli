from __future__ import annotations

import subprocess
from typing import Any

import click

from ..adapters import RepoAdapter
from ..adapters.capabilities import unsupported
from ..errors import RepoResolutionError
from ..formatters import format_repo_detail, format_repo_list, output_result, repo_visibility
from ..helptext import GCSectionGroup, set_gc_help
from ..repo import parse_remote_url_with_host, parse_repo_with_host, resolve_repo
from ..services import RepoService
from ..utils import open_in_browser, prompt_if_missing, safe_echo

REPO_VIEW_JSON_FIELDS = [
    "id",
    "name",
    "nameWithOwner",
    "description",
    "isPrivate",
    "visibility",
    "defaultBranch",
    "homepage",
    "isFork",
    "isArchived",
    "stargazers",
    "forks",
    "openIssues",
    "license",
    "owner",
    "url",
    "createdAt",
    "updatedAt",
    "pushedAt",
]

REPO_LIST_JSON_FIELDS = [
    field for field in REPO_VIEW_JSON_FIELDS if field not in {"isArchived", "createdAt", "pushedAt"}
]


def _is_gitcode_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    return normalized == "gitcode.com" or normalized.endswith(".gitcode.com")


def _parse_repository_arg(repository: str) -> tuple[str, str]:
    """Parse OWNER/REPO, HOST/OWNER/REPO, or a gitcode.com URL into (owner, repo)."""
    value = repository.strip()
    try:
        host, owner, name = parse_remote_url_with_host(value)
    except RepoResolutionError:
        try:
            host, owner, name = parse_repo_with_host(value)
        except RepoResolutionError as exc:
            raise click.ClickException(
                "Invalid repository format. Use OWNER/REPO, HOST/OWNER/REPO, or a gitcode.com URL."
            ) from exc
    if host and not _is_gitcode_host(host):
        raise click.ClickException(
            f"Repository host '{host}' is not supported; gc works with gitcode.com repositories."
        )
    return owner, name


def _resolve_repo_target(app, repo_name: str | None, repository: str | None) -> tuple[str, str]:
    if repository:
        return _parse_repository_arg(repository)
    return resolve_repo(repo_name or app.repo)


def _normalize_repo_owner(item: dict) -> Any:
    owner = item.get("owner") or item.get("namespace")
    if not isinstance(owner, dict):
        return owner
    login = owner.get("login") or owner.get("username") or owner.get("path") or owner.get("name")
    return {
        "id": owner.get("id"),
        "is_bot": bool(owner.get("is_bot", False)),
        "login": login,
        "name": owner.get("name") or login,
    }


def _is_archived(item: dict) -> bool:
    if item.get("archived") is not None:
        return bool(item.get("archived"))
    # GitCode exposes archive state only through the Chinese-labeled `status` field
    # (e.g. 已归档); treat unrecognized values as not archived.
    return "归档" in str(item.get("status") or "")


def _normalize_repo_fields(item: dict) -> dict:
    namespace = item.get("namespace")
    owner = item.get("owner")
    owner_path = None
    if isinstance(namespace, dict):
        owner_path = namespace.get("path") or namespace.get("name")
    elif isinstance(owner, dict):
        owner_path = owner.get("login") or owner.get("name")
    elif isinstance(owner, str):
        owner_path = owner
    name = item.get("name")
    name_with_owner = item.get("full_name") or (f"{owner_path}/{name}" if owner_path and name else name)
    return {
        "id": item.get("id"),
        "name": name,
        "nameWithOwner": name_with_owner,
        "description": item.get("description"),
        "isPrivate": bool(item.get("private")),
        "visibility": repo_visibility(item).upper(),
        "defaultBranch": item.get("default_branch"),
        "homepage": item.get("homepage"),
        "isFork": bool(item.get("fork")),
        "isArchived": _is_archived(item),
        "stargazers": item.get("stargazers_count"),
        "forks": item.get("forks_count"),
        "openIssues": item.get("open_issues_count"),
        "license": item.get("license"),
        "owner": _normalize_repo_owner(item),
        "url": item.get("html_url") or item.get("web_url"),
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "pushedAt": item.get("pushed_at"),
    }


def _normalize_repo_list(items: list[dict]) -> list[dict]:
    return [_normalize_repo_fields(item) for item in items]


def _echo_repo_list(items: list[dict]) -> None:
    output = format_repo_list(items)
    if output:
        safe_echo(output)


def _require_valid_limit(limit: int | None) -> None:
    if limit is not None and limit < 1:
        raise click.BadParameter("must be greater than 0", param_hint="--limit")


def _check_bare_json(json_fields: str | None, fields: list[str]) -> None:
    if json_fields == "":
        safe_echo("Available fields: " + ", ".join(fields))
        raise click.exceptions.Exit(1)


def _git_clone(url: str, *extra_args: str) -> None:
    exit_code = subprocess.call(["git", "clone", url, *extra_args])
    if exit_code != 0:
        raise SystemExit(exit_code)


def _replace_repo_in_url(url: str, repo: str, new_name: str) -> str:
    for suffix in (f"{repo}.git", repo):
        if url.endswith(suffix):
            replacement = f"{new_name}.git" if suffix.endswith(".git") else new_name
            return url[: -len(suffix)] + replacement
    return url


def _update_origin_remote(owner: str, repo: str, new_name: str) -> None:
    """Best-effort: point the local `origin` remote at the renamed repository."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return
    url = result.stdout.strip()
    try:
        _, origin_owner, origin_repo = parse_remote_url_with_host(url)
    except RepoResolutionError:
        return
    if (origin_owner, origin_repo) != (owner, repo):
        return
    new_url = _replace_repo_in_url(url, repo, new_name)
    try:
        subprocess.run(
            ["git", "remote", "set-url", "origin", new_url],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return
    safe_echo(f"Updated the 'origin' remote URL to {new_url}")


def _repo_url(item: dict | None, owner: str, repo: str) -> str:
    if isinstance(item, dict):
        url = item.get("html_url") or item.get("web_url")
        if url:
            return str(url)
    return f"https://gitcode.com/{owner}/{repo}"


def _fork_full_name(item: dict | None, repo: str) -> str:
    if isinstance(item, dict):
        full_name = item.get("full_name")
        if full_name:
            return str(full_name)
        namespace = item.get("namespace") or item.get("owner")
        if isinstance(namespace, dict):
            path = namespace.get("path") or namespace.get("login") or namespace.get("name")
            name = item.get("path") or item.get("name") or repo
            if path:
                return f"{path}/{name}"
    return repo


@click.group("repo", cls=GCSectionGroup, help="Work with GitCode repositories.")
def repo_group() -> None:
    pass


@repo_group.command("view")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("repository", required=False)
@click.option("-w", "--web", is_flag=True, help="Open the repository in the web browser.")
@click.option(
    "--json",
    "json_fields",
    is_flag=False,
    flag_value="",
    default=None,
    help="Output JSON. Optionally specify comma-separated fields.",
)
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def repo_view(
    ctx: click.Context,
    repo_name: str | None,
    repository: str | None,
    web: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    app = ctx.obj["app"]
    _check_bare_json(json_fields, getattr(repo_view, "gc_json_fields", []))
    owner, repo = _resolve_repo_target(app, repo_name, repository)
    if web:
        open_in_browser(f"https://gitcode.com/{owner}/{repo}")
        return
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    item = adapter.view(owner, repo)
    output_item = _normalize_repo_fields(item) if item and (json_fields or jq_query or template) else item

    def default_formatter(data: dict) -> None:
        safe_echo(format_repo_detail(data))
        readme = adapter.get_readme(owner, repo, item if isinstance(item, dict) else None)
        if readme:
            safe_echo("")
            safe_echo("README:")
            safe_echo(readme)

    output_result(
        output_item,
        json_fields,
        jq_query,
        template,
        default_formatter=default_formatter,
    )


@repo_group.command("list")
@click.argument("owner", required=False)
@click.option("-L", "--limit", type=int, default=30, show_default=True, help="Maximum number of repositories to list.")
@click.option(
    "--visibility",
    type=click.Choice(["public", "private", "internal"]),
    help="Filter by repository visibility (applied client-side).",
)
@click.option("-l", "--language", help="Filter by primary coding language (applied client-side).")
@click.option("--fork", "fork_only", is_flag=True, help="Show only forks.")
@click.option("--source", is_flag=True, help="Show only non-forks.")
@click.option(
    "--json",
    "json_fields",
    is_flag=False,
    flag_value="",
    default=None,
    help="Output JSON. Optionally specify comma-separated fields.",
)
@click.option("-q", "--jq", "jq_query", help="Filter JSON output using a jq expression.")
@click.option("-t", "--template", help="Format output using a Go template string.")
@click.pass_context
def repo_list(
    ctx: click.Context,
    owner: str | None,
    limit: int | None,
    visibility: str | None,
    language: str | None,
    fork_only: bool,
    source: bool,
    json_fields: str | None,
    jq_query: str | None,
    template: str | None,
) -> None:
    _check_bare_json(json_fields, getattr(repo_list, "gc_json_fields", []))
    _require_valid_limit(limit)
    if fork_only and source:
        raise click.UsageError("specify only one of --fork or --source")
    if owner and "/" in owner:
        raise click.UsageError("owner must be a username or organization, not OWNER/REPO")
    service = RepoService(ctx.obj["app"].client())
    adapter = RepoAdapter(service)
    items = adapter.list_repos(
        owner,
        limit=limit,
        fork=fork_only,
        source=source,
        visibility=visibility,
        language=language,
    )
    output_items = _normalize_repo_list(items) if json_fields or jq_query or template else items
    output_result(
        output_items,
        json_fields,
        jq_query,
        template,
        default_formatter=_echo_repo_list,
    )


def _resolve_created_owner(item: dict | None, target_owner: str | None) -> str | None:
    """Derive the owner of a freshly created repository from the API response."""
    owner = target_owner
    if not item or owner:
        return owner
    namespace = item.get("namespace") or item.get("owner")
    if isinstance(namespace, dict):
        owner = namespace.get("path") or namespace.get("login") or namespace.get("name")
    elif isinstance(namespace, str) and namespace:
        owner = namespace
    if not owner:
        full_name = item.get("full_name") or item.get("path_with_namespace")
        if isinstance(full_name, str) and "/" in full_name:
            owner = full_name.split("/", 1)[0]
    return owner


@repo_group.command("create")
@click.argument("name", required=False)
@click.option("-d", "--description", help="Description of the repository.")
@click.option("--public", "public_repo", is_flag=True, help="Make the new repository public.")
@click.option("--private", "private_repo", is_flag=True, help="Make the new repository private (the default).")
@click.option("--internal", is_flag=True, help="Unsupported: GitCode has no internal repositories.")
@click.option("--add-readme", is_flag=True, help="Add a README file to the new repository.")
@click.option("--homepage", help="Repository home page URL. The gh -h short flag is reserved for help in gc.")
@click.option("--disable-issues", is_flag=True, help="Disable issues in the new repository.")
@click.option("--disable-wiki", is_flag=True, help="Disable wiki in the new repository.")
@click.option("-g", "--gitignore", "gitignore_template", help="Specify a gitignore template for the repository.")
@click.option("-l", "--license", "license_template", help="Specify an Open Source License for the repository.")
@click.option("-c", "--clone", is_flag=True, help="Clone the new repository to the current directory.")
@click.pass_context
def repo_create(
    ctx: click.Context,
    name: str | None,
    description: str | None,
    public_repo: bool,
    private_repo: bool,
    internal: bool,
    add_readme: bool,
    homepage: str | None,
    disable_issues: bool,
    disable_wiki: bool,
    gitignore_template: str | None,
    license_template: str | None,
    clone: bool,
) -> None:
    app = ctx.obj["app"]
    if internal:
        raise unsupported("REPO_CREATE_INTERNAL")
    if public_repo and private_repo:
        raise click.UsageError("specify only one of --public or --private")
    name = prompt_if_missing(name, "Repository name")
    target_owner: str | None = None
    repo_name = name
    if "/" in name:
        target_owner, repo_name = _parse_repository_arg(name)
    private: bool = not public_repo
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    item = adapter.create_repo(
        repo_name,
        target_owner,
        description=description,
        private=private,
        auto_init=add_readme,
        homepage=homepage,
        has_issues=False if disable_issues else None,
        has_wiki=False if disable_wiki else None,
        gitignore_template=gitignore_template,
        license_template=license_template,
    )
    item_dict = item if isinstance(item, dict) else None
    owner = _resolve_created_owner(item_dict, target_owner)
    if owner:
        safe_echo(_repo_url(item_dict, owner, repo_name))
    elif item_dict and (item_dict.get("html_url") or item_dict.get("web_url")):
        safe_echo(str(item_dict.get("html_url") or item_dict.get("web_url")))
    else:
        safe_echo(f"Created repository {repo_name}")
    if clone:
        clone_url = None
        if item_dict:
            clone_url = item_dict.get("http_url_to_repo") or item_dict.get("ssh_url_to_repo")
        _git_clone(
            str(clone_url) if clone_url else f"https://gitcode.com/{owner or ''}/{repo_name}".rstrip("/") + ".git"
        )


@repo_group.command("clone", context_settings={"ignore_unknown_options": True})
@click.argument("repository")
@click.argument("directory", required=False)
@click.argument("gitflags", nargs=-1, type=click.UNPROCESSED)
def repo_clone(repository: str, directory: str | None, gitflags: tuple[str, ...]) -> None:
    owner, repo = _parse_repository_arg(repository)
    # With ignore_unknown_options, click may stuff a passthrough flag into the
    # optional `directory` positional; prepending whatever landed there keeps
    # the original argument order for `git clone`.
    clone_args: list[str] = [directory] if directory else []
    clone_args.extend(arg for arg in gitflags if arg != "--")
    _git_clone(f"https://gitcode.com/{owner}/{repo}.git", *clone_args)


@repo_group.command("fork", context_settings={"ignore_unknown_options": True})
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("repository", required=False)
@click.argument("gitflags", nargs=-1, type=click.UNPROCESSED)
@click.option("--clone", is_flag=True, help="Clone the fork.")
@click.option("--org", help="Create the fork in an organization.")
@click.option("--fork-name", help="Unsupported: GitCode cannot rename a fork during creation.")
@click.option("--default-branch-only", is_flag=True, help="Unsupported: GitCode forks copy every branch.")
@click.pass_context
def repo_fork(
    ctx: click.Context,
    repo_name: str | None,
    repository: str | None,
    gitflags: tuple[str, ...],
    clone: bool,
    org: str | None,
    fork_name: str | None,
    default_branch_only: bool,
) -> None:
    if fork_name is not None:
        raise unsupported("REPO_FORK_NAME")
    if default_branch_only:
        raise unsupported("REPO_FORK_DEFAULT_BRANCH_ONLY")
    app = ctx.obj["app"]
    owner, repo = _resolve_repo_target(app, repo_name, repository)
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    result = adapter.fork_repo(owner, repo, org=org)
    item = result.item if isinstance(result.item, dict) else None
    full_name = _fork_full_name(item, repo)
    safe_echo(f"✓ Created fork {full_name}")
    if clone:
        clone_url = None
        if item:
            clone_url = item.get("http_url_to_repo")
        fork_owner, fork_name_part = full_name.rsplit("/", 1) if "/" in full_name else (owner, full_name)
        _git_clone(
            str(clone_url) if clone_url else f"https://gitcode.com/{fork_owner}/{fork_name_part}.git",
            *(arg for arg in gitflags if arg != "--"),
        )


@repo_group.command("edit")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("repository", required=False)
@click.option("-d", "--description", help="New description of the repository.")
@click.option("--homepage", help="New home page URL. The gh -h short flag is reserved for help in gc.")
@click.option("--default-branch", help="New default branch name.")
@click.option("--visibility", type=click.Choice(["public", "private"]), help="Change repository visibility.")
@click.option(
    "--enable-issues/--disable-issues",
    "enable_issues",
    default=None,
    help="Enable or disable issues.",
)
@click.option("--enable-wiki/--disable-wiki", "enable_wiki", default=None, help="Enable or disable wiki.")
@click.pass_context
def repo_edit(
    ctx: click.Context,
    repo_name: str | None,
    repository: str | None,
    description: str | None,
    homepage: str | None,
    default_branch: str | None,
    visibility: str | None,
    enable_issues: bool | None,
    enable_wiki: bool | None,
) -> None:
    app = ctx.obj["app"]
    owner, repo = _resolve_repo_target(app, repo_name, repository)
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    adapter.edit_repo(
        owner,
        repo,
        description=description,
        homepage=homepage,
        default_branch=default_branch,
        private=None if visibility is None else visibility == "private",
        has_issues=enable_issues,
        has_wiki=enable_wiki,
    )
    safe_echo(f"Edited repository {owner}/{repo}")


@repo_group.command("rename")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("new_name", required=False)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def repo_rename(ctx: click.Context, repo_name: str | None, new_name: str | None, yes: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    new_name = prompt_if_missing(new_name, "New repository name")
    if not yes and not click.confirm(f"Rename {owner}/{repo} to {new_name}?", default=False):
        raise click.ClickException("Aborted.")
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    adapter.rename_repo(owner, repo, new_name)
    safe_echo(f"✓ Renamed repository {owner}/{new_name}")
    _update_origin_remote(owner, repo, new_name)


@repo_group.command("delete")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("repository", required=False)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def repo_delete(ctx: click.Context, repo_name: str | None, repository: str | None, yes: bool) -> None:
    app = ctx.obj["app"]
    owner, repo = _resolve_repo_target(app, repo_name, repository)
    target = f"{owner}/{repo}"
    if not yes and not click.confirm(f"Delete repository {target}?", default=False):
        raise click.ClickException("Aborted.")
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    adapter.delete_repo(owner, repo)
    safe_echo(f"Deleted repository {target}")


@repo_group.command("sync")
@click.option("-R", "--repo", "repo_name", help="Select another repository using the [HOST/]OWNER/REPO format.")
@click.argument("repository", required=False)
@click.pass_context
def repo_sync(ctx: click.Context, repo_name: str | None, repository: str | None) -> None:
    app = ctx.obj["app"]
    owner, repo = _resolve_repo_target(app, repo_name, repository)
    service = RepoService(app.client())
    adapter = RepoAdapter(service)
    adapter.sync_repo(owner, repo)
    safe_echo(f'✓ Synced the "{owner}/{repo}" repository from its upstream source')


set_gc_help(
    repo_group,
    gc_usage="gc repo <command> [flags]",
    gc_command_sections=[
        ("GENERAL COMMANDS", ["clone", "create", "fork", "list"]),
        ("TARGETED COMMANDS", ["delete", "edit", "rename", "sync", "view"]),
    ],
    gc_examples=[
        "gc repo list",
        "gc repo view owner/repo --web",
        "gc repo clone owner/repo",
    ],
    gc_arguments_help=[
        "A repository can be supplied as argument in any of the following formats:",
        '- by name, e.g. "OWNER/REPO" or "HOST/OWNER/REPO"; or',
        '- by URL, e.g. "https://gitcode.com/OWNER/REPO".',
        "When omitted, gc resolves the repository from the git origin remote.",
    ],
)

repo_view.short_help = "View a repository"
repo_view.help = "View a repository. With no argument, the repository is taken from the git origin remote."
set_gc_help(
    repo_view,
    gc_usage="gc repo view [{<repository> | -R OWNER/REPO}] [flags]",
    gc_json_fields=REPO_VIEW_JSON_FIELDS,
)
repo_list.short_help = "List repositories owned by user or organization"
repo_list.help = (
    "List repositories owned by user or organization. With no argument, lists repositories of the authenticated user."
)
set_gc_help(
    repo_list,
    gc_usage="gc repo list [<owner>] [flags]",
    gc_json_fields=REPO_LIST_JSON_FIELDS,
    gc_examples=[
        "gc repo list",
        "gc repo list owner",
        "gc repo list --limit 10 --visibility private",
    ],
)
repo_create.short_help = "Create a new repository"
repo_create.help = (
    "Create a new repository. Pass OWNER/NAME to create inside an organization."
    " New repositories are private unless --public is given."
)
set_gc_help(
    repo_create,
    gc_usage="gc repo create [{<name> | <owner>/<name>}] [flags]",
    gc_examples=[
        "gc repo create my-project --public --add-readme",
        'gc repo create my-org/my-project -d "Description"',
    ],
)
repo_clone.short_help = "Clone a repository locally"
repo_clone.help = "Clone a gitcode.com repository locally, passing extra flags to git clone after --."
set_gc_help(
    repo_clone,
    gc_usage="gc repo clone <repository> [<directory>] [-- <gitflags>...] [flags]",
)
repo_fork.short_help = "Create a fork of a repository"
repo_fork.help = "Create a fork of a repository. With no argument, the repository is taken from the git origin remote."
set_gc_help(
    repo_fork,
    gc_usage="gc repo fork [{<repository> | -R OWNER/REPO}] [flags]",
)
repo_edit.short_help = "Edit repository settings"
repo_edit.help = "Edit repository settings. With no argument, the repository is taken from the git origin remote."
repo_rename.short_help = "Rename a repository"
repo_rename.help = "Rename a repository, updating the local origin remote URL when it points at the old name."
set_gc_help(
    repo_rename,
    gc_usage="gc repo rename [{<new-name> | -R OWNER/REPO <new-name>}] [flags]",
)
repo_delete.short_help = "Delete a repository"
repo_delete.help = "Delete a repository. With no argument, the repository is taken from the git origin remote."
set_gc_help(
    repo_delete,
    gc_usage="gc repo delete [{<repository> | -R OWNER/REPO}] [flags]",
)
repo_sync.short_help = "Sync a forked repository"
repo_sync.help = (
    "Sync a forked repository from its upstream source using the GitCode fork sync API."
    " Branch selection and local sync are not supported."
)
set_gc_help(
    repo_sync,
    gc_usage="gc repo sync [{<repository> | -R OWNER/REPO}] [flags]",
)
