"""Search GitCode's documented global keyword indexes."""

from __future__ import annotations

import re

import click

from ..helptext import GCSectionGroup, set_gc_help
from ..json_projection import project_issue, project_pr
from ..repo import resolve_repo
from ..services.search import MAX_PAGES, MAX_PULL_RESULTS, PAGE_SIZES, SearchService, search_pulls
from ..utils import safe_echo
from ._listing_output import listing_options, render_listing, selected_fields

# Deliberately smaller than GitHub's sets; the search response is not a full repository or issue.
_FIELDS = {
    "repositories": (
        "id",
        "name",
        "fullName",
        "description",
        "url",
        "createdAt",
        "updatedAt",
        "pushedAt",
        "defaultBranch",
        "forksCount",
        "isFork",
        "stargazersCount",
        "openIssuesCount",
        "watchersCount",
    ),
    "issues": (
        "id",
        "number",
        "title",
        "state",
        "body",
        "repository",
        "labels",
        "commentsCount",
        "url",
        "createdAt",
        "updatedAt",
    ),
    "users": ("id", "login", "name", "url", "createdAt", "avatarUrl"),
    "pulls": (
        "id",
        "number",
        "title",
        "state",
        "body",
        "author",
        "repository",
        "labels",
        "commentsCount",
        "url",
        "createdAt",
        "updatedAt",
        "headRefName",
        "baseRefName",
    ),
}
_COLUMNS = {
    "repositories": ("fullName", "description"),
    "issues": ("repository", "number", "state", "title"),
    "users": ("login", "name", "url"),
    "pulls": ("repository", "number", "state", "title"),
}


def _project(resource: str, item: dict) -> dict:
    if resource == "pulls":
        pr = project_pr({**item, "number": item.get("iid")})
        path = item.get("path_with_namespace")
        pr["repository"] = (
            {"nameWithOwner": path, "name": path.rsplit("/", 1)[-1]} if isinstance(path, str) and path else None
        )
        state = item.get("state")
        pr["state"] = state.upper() if state in ("open", "merged", "closed") else None
        pr["commentsCount"] = item.get("comment_num")
        return {key: pr.get(key) for key in _FIELDS[resource]}
    if resource == "issues":
        issue = project_issue(item)
        repo = item.get("repository") or {}
        issue["repository"] = (
            {"name": repo.get("name"), "nameWithOwner": repo.get("full_name")} if isinstance(repo, dict) else None
        )
        issue["commentsCount"] = item.get("comments")
        return {key: issue.get(key) for key in _FIELDS[resource]}
    aliases = {
        "fullName": "full_name",
        "url": "web_url" if resource == "repositories" else "html_url",
        "defaultBranch": "default_branch",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
        "pushedAt": "pushed_at",
        "stargazersCount": "stargazers_count",
        "forksCount": "forks_count",
        "openIssuesCount": "open_issues_count",
        "watchersCount": "watchers_count",
        "avatarUrl": "avatar_url",
    }
    result = {key: item.get(aliases.get(key, key)) for key in _FIELDS[resource]}
    if resource == "repositories":
        # The two published search schemas use a boolean or an integer flag.
        fork = item.get("fork")
        result["isFork"] = bool(fork) if type(fork) in (bool, int) and fork in (0, 1) else None
    return result


def _show_rows(resource: str, rows: list[dict]) -> None:
    for row in rows:
        display = dict(row)
        if resource in {"issues", "pulls"}:
            display["repository"] = (row["repository"] or {}).get("nameWithOwner")
            display["number"] = f"#{row['number']}" if row["number"] is not None else ""
        safe_echo("\t".join(str(display[col]) if display[col] is not None else "" for col in _COLUMNS[resource]))


def _run(ctx, resource, keywords, limit, order, json_fields, jq_query, template, **filters):
    fields = selected_fields(json_fields, _FIELDS[resource], jq_query, template)
    query = " ".join(keywords).strip()
    if not query:
        raise click.UsageError("A search keyword is required by GitCode.")
    if re.search(r"(?:^|\s)-?[a-zA-Z][\w-]*:(?!//)\S+", query):
        raise click.UsageError("Raw search qualifiers are not supported. Use the documented command flags.")
    if ctx.obj["app"].repo and resource != "issues":
        raise click.UsageError("The repository filter applies only to search issues.")
    if resource == "issues":
        explicit_repo = filters.get("repo") or ctx.obj["app"].repo
        if explicit_repo:
            filters["repo"] = "/".join(resolve_repo(explicit_repo))
    client = ctx.obj["app"].client()
    if resource == "pulls":
        rows = search_pulls(client, query, limit, sort=filters.get("sort"), order=order)
    else:
        rows = SearchService(client).search(resource, query, limit, order=order, **filters)
    render_listing(
        [_project(resource, row) for row in rows], fields, jq_query, template, lambda data: _show_rows(resource, data)
    )


def _options(resource):
    def decorate(f):
        f = click.argument("keywords", nargs=-1, required=True)(f)
        f = click.option("--order", type=click.Choice(["asc", "desc"]), help="Order of the sorted results.")(f)
        f = click.option(
            "--limit",
            "-L",
            default=30,
            show_default=True,
            type=click.IntRange(1, MAX_PULL_RESULTS if resource == "pulls" else PAGE_SIZES[resource] * MAX_PAGES),
            help="Maximum number of results.",
        )(f)
        return listing_options(f)

    return decorate


@click.group(
    "search",
    cls=GCSectionGroup,
    help="Search GitCode by keyword. Raw GitHub qualifiers and global commit and code search are not supported.",
)
def search_group():
    pass


@search_group.command("repos")
@_options("repositories")
@click.option("--owner", multiple=True, help="Restrict to one owner or organization path.")
@click.option("--language", help="Restrict to repositories in a language.")
@click.option(
    "--include-forks",
    type=click.Choice(["false"]),
    help="Request non-forks and verify the returned rows. Including or selecting only forks is not supported.",
)
@click.option(
    "--sort",
    type=click.Choice(["best-match", "updated", "stars", "forks"]),
    help="Sort matching repositories. Watch counts are available with --json watchersCount, not as a sort key.",
)
@click.pass_context
def search_repos(ctx, owner, language, include_forks, sort, **options):
    """Find repositories across GitCode."""
    if len(owner) > 1:
        raise click.UsageError("GitCode search supports a single --owner.")
    order_by = {"updated": "last_push_at", "stars": "stars_count", "forks": "forks_count"}.get(sort)
    _run(
        ctx,
        "repositories",
        owner=owner[0] if owner else None,
        language=language,
        fork=include_forks,
        sort=order_by,
        **options,
    )


@search_group.command("issues")
@_options("issues")
@click.option("--repo", "-R", multiple=True, help="Restrict to one [HOST/]OWNER/REPO.")
@click.option("--state", type=click.Choice(["open", "closed"]), help="Restrict to an issue state.")
@click.option("--sort", type=click.Choice(["best-match", "created", "updated"]), help="Sort matching issues.")
@click.pass_context
def search_issues(ctx, repo, state, sort, **options):
    """Find issues across GitCode (does not include pull requests)."""
    if len(repo) > 1:
        raise click.UsageError("GitCode search supports a single --repo.")
    order_by = {"created": "created_at", "updated": "last_push_at"}.get(sort)
    _run(ctx, "issues", repo=repo[0] if repo else None, state=state, sort=order_by, **options)


@search_group.command("users")
@_options("users")
@click.option("--sort", type=click.Choice(["best-match", "joined"]), help="Sort matching users.")
@click.pass_context
def search_users(ctx, sort, **options):
    """Find users across GitCode (GitCode-specific)."""
    _run(ctx, "users", sort="joined_at" if sort == "joined" else None, **options)


@search_group.command("prs")
@_options("pulls")
@click.option("--sort", type=click.Choice(["best-match", "created", "updated"]), help="Sort matching pull requests.")
@click.pass_context
def search_prs(ctx, sort, **options):
    """Find pull requests across GitCode. The global API accepts keywords, not state or repository filters."""
    order_by = {"created": "created_at", "updated": "updated_at"}.get(sort)
    _run(ctx, "pulls", sort=order_by, **options)


for _resource, _command in (
    ("repositories", search_repos),
    ("issues", search_issues),
    ("users", search_users),
    ("pulls", search_prs),
):
    set_gc_help(_command, gc_json_fields=_FIELDS[_resource])
