"""Native GitCode Actions, with bounded reads and separate v5 PR gates."""

from __future__ import annotations

import json
from contextlib import closing, contextmanager
from functools import partial
from pathlib import Path
from typing import Any

import click

from .._redact import redact
from ..actions_client import ActionsClient
from ..actions_watch import MAX_INTERVAL, MAX_TIMEOUT, watch_run
from ..adapters.action_checks import CHECK_ROW_FIELDS, check_rows, pr_evidence
from ..context import AppContext
from ..helptext import GCSectionCommand, GCSectionGroup, set_gc_help
from ..repo import resolve_repo
from ..services.actions import MAX_WORKFLOW_SCAN, SHA_RE, ActionsService

repo_option = click.option("-R", "--repo", "repo_name", help="[HOST/]OWNER/REPO (defaults to origin).")
page_option = click.option("--page", type=click.IntRange(1), default=1, show_default=True)
limit_option = click.option("-L", "--limit", type=click.IntRange(1, 100), default=20, show_default=True)
offset_option = click.option("--offset", type=click.IntRange(0), default=0, show_default=True)


@contextmanager
def _open_service(owner: str, repo: str, token: str):
    with closing(ActionsClient(token)) as client:
        yield ActionsService(client, owner, repo)


def _service(ctx: click.Context, repo_name: str | None):
    app: AppContext = ctx.obj["app"]
    return _open_service(*resolve_repo(repo_name or app.repo), app.token)


def _show(ctx: click.Context, value: dict | list):
    # Escaped JSON (including log lines) is intentional: never interpret terminal controls or
    # emit the request credential if a workflow or an upstream error reflects it in output.
    def scrub(item: Any) -> Any:
        if isinstance(item, str):
            return redact(item, ctx.obj["app"].token)
        if isinstance(item, list):
            return [scrub(v) for v in item]
        if isinstance(item, dict):
            return {k: scrub(v) for k, v in item.items()}
        return item

    click.echo(json.dumps(scrub(value), indent=2, ensure_ascii=True))


@click.group(cls=GCSectionGroup, short_help="Inspect or manage GitCode Actions runs")
def run():
    """Inspect, rerun, or stop GitCode Actions runs. Inspect jobs and step logs."""


@run.command("list")
@repo_option
@page_option
@limit_option
@click.option("-b", "--branch")
@click.option("-w", "--workflow", help="GitCode workflow ID.")
@click.option("-e", "--event", type=click.Choice(["MR", "Push", "Manual"]))
@click.option("-s", "--status", help="GitCode status, e.g. FAILED.")
@click.option("--pr", type=click.IntRange(1), help="PR number, not database ID.")
@click.pass_context
def run_list(ctx, repo_name, page, limit, branch, workflow, event, status, pr):
    """List one page of runs, with a continuation page when available."""
    with _service(ctx, repo_name) as svc:
        _show(
            ctx,
            svc.page(
                "runs", page, limit, branch=branch, workflow_id=workflow, event=event, status=status, pull_request_id=pr
            ),
        )


@run.command("view")
@click.argument("run_id")
@repo_option
@click.option(
    "-a", "--attempt", type=click.IntRange(0), help="Require this current attempt; historical lookup unavailable."
)
@click.option("--commit", help="Require this full head commit SHA.")
@click.option("-j", "--job", "job_id", help="Inspect one job's steps instead of listing jobs.")
@click.option("--log", "log_requested", is_flag=True, help="Read a page of one step log (requires --job and --step).")
@click.option("--step", help="Step run ID for --log.")
@offset_option
@limit_option
@click.option("--sort", type=click.Choice(["asc", "desc"]), default="asc")
@click.pass_context
def run_view(ctx, repo_name, run_id, attempt, commit, job_id, log_requested, step, offset, limit, sort):
    """Show the current run/attempt and jobs, one job's steps, or a bounded log page."""
    if (log_requested and not (job_id and step)) or (not log_requested and step):
        raise click.UsageError("--log needs --job and --step; --step requires --log.")
    if sort != "asc" and not log_requested:
        raise click.UsageError("--sort desc applies only to --log.")
    with _service(ctx, repo_name) as svc:
        pinned = svc.pin(run_id, attempt, commit)
        if job_id:
            job = svc.job(run_id, job_id)
            extra = svc.logs(run_id, job, step, offset, limit, sort) if log_requested else svc.steps(job, offset, limit)
        else:
            extra = svc.jobs(run_id, offset, limit)
        latest = svc.pin(run_id, pinned["attempt"], pinned["head_sha"])
        _show(ctx, {"run": latest, **extra})


@run.command("watch")
@click.argument("run_id")
@repo_option
@click.option(
    "-i",
    "--interval",
    type=click.IntRange(1, MAX_INTERVAL),
    default=3,
    show_default=True,
    help="Seconds between run-detail reads.",
)
@click.option(
    "--timeout",
    type=click.IntRange(1, MAX_TIMEOUT),
    default=300,
    show_default=True,
    help="Local watch deadline in seconds; never cancels the remote run.",
)
@click.option("--exit-status", is_flag=True, help="Return nonzero for FAILED or CANCELED (IGNORED is always nonzero).")
@click.pass_context
def run_watch(ctx: click.Context, repo_name, run_id, interval, timeout, exit_status):
    """Watch one explicit run ID. Exit 0 means a terminal state was observed, not that PR checks passed.

    Use --exit-status to also return nonzero for FAILED or CANCELED.
    """
    app: AppContext = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    try:
        result = watch_run(
            partial(_open_service, owner, repo, app.token),
            run_id,
            interval,
            timeout,
            lambda status: click.echo(f"Run status: {status}", err=True),
        )
    except KeyboardInterrupt:
        click.echo("Watch interrupted locally; no stop request was sent.", err=True)
        ctx.exit(130)
    _show(ctx, result)
    if result["status"] == "IGNORED":
        ctx.exit(3)
    if exit_status and result["status"] in {"FAILED", "CANCELED"}:
        ctx.exit(1)


@run.command("rerun")
@click.argument("run_id")
@repo_option
@click.option("--attempt", type=click.IntRange(0), required=True, help="Expected current attempt.")
@click.option("--commit", required=True, help="Expected full commit SHA.")
@click.option("--job-run-id", multiple=True, help="Retry an explicitly observed failed job-run ID (repeatable).")
@click.pass_context
def run_rerun(ctx, repo_name, run_id, attempt, commit, job_run_id):
    """Request one rerun. Without --job-run-id, reruns the ENTIRE run."""
    with _service(ctx, repo_name) as svc:
        _show(ctx, svc.rerun(run_id, attempt, commit, job_run_id))


@run.command("cancel")
@click.argument("run_id")
@repo_option
@click.option("--attempt", type=click.IntRange(0), required=True, help="Expected current attempt.")
@click.option("--commit", required=True, help="Expected full commit SHA.")
@click.option("--yes", is_flag=True, help="Explicitly authorize sending one stop request without prompting.")
@click.pass_context
def run_cancel(ctx, repo_name, run_id, attempt, commit, yes):
    """Request one GitCode stop, then check whether the same run attempt is CANCELED."""
    if not SHA_RE.fullmatch(commit):
        raise click.UsageError("--commit requires a full hexadecimal commit SHA.")
    with _service(ctx, repo_name) as svc:
        svc.client.require_token()  # Missing credentials must not cause even a read.
        if not yes:
            target = f"{svc.owner}/{svc.repo}, run {run_id}, attempt {attempt}, commit {commit}"
            safe_target = json.dumps(redact(target, ctx.obj["app"].token), ensure_ascii=True)
            click.confirm(
                f"Stop {safe_target}? GitCode cannot atomically pin the attempt on stop", abort=True, err=True
            )
        result = svc.cancel(run_id, attempt, commit)
    _show(ctx, result)
    if result["result"] == "requested_not_confirmed":
        ctx.exit(3)


@click.group(cls=GCSectionGroup, short_help="Inspect or dispatch GitCode workflows")
def workflow():
    """List or view workflow definitions, or explicitly dispatch GitCode workflows."""


@workflow.command("list")
@repo_option
@page_option
@limit_option
@click.pass_context
def workflow_list(ctx, repo_name, page, limit):
    """List one page of workflow definitions, not runs."""
    with _service(ctx, repo_name) as svc:
        _show(ctx, svc.page("workflows", page, limit))


@workflow.command("view")
@click.argument("selector")
@repo_option
@click.option("--scan-limit", type=click.IntRange(1, MAX_WORKFLOW_SCAN), default=100, show_default=True)
@click.pass_context
def workflow_view(ctx, repo_name, selector, scan_limit):
    """Find exact workflow metadata by ID, name, or filename. Does not return YAML."""
    with _service(ctx, repo_name) as svc:
        _show(ctx, svc.workflow(selector, scan_limit))


@workflow.command("run")
@click.argument("workflow_id")
@repo_option
@click.option("-r", "--ref", required=True, help="Exact branch or tag to dispatch.")
@click.option("-f", "--raw-field", multiple=True, help="String input name=value; repeat for distinct inputs.")
@click.pass_context
def workflow_run(ctx, repo_name, workflow_id, ref, raw_field):
    """Dispatch once by workflow ID or YAML filename. No default branch is assumed."""
    inputs = {}
    for field in raw_field:
        name, sep, value = field.partition("=")
        if not sep or not name.strip() or name in inputs:
            raise click.UsageError("Use distinct nonempty input names in --raw-field name=value.")
        inputs[name] = value
    with _service(ctx, repo_name) as svc:
        _show(ctx, svc.dispatch(workflow_id, ref, inputs))


@click.command("checks", cls=GCSectionCommand, short_help="Report GitCode CI evidence for a pull request")
@click.argument("number", type=click.IntRange(1))
@repo_option
@click.option("--scan-limit", type=click.IntRange(1, 100), default=100, show_default=True)
@click.option("--json", "selections", multiple=True, metavar="FIELDS", help="Select fields for observed workflow runs.")
@click.pass_context
def pr_checks(ctx, number, repo_name, scan_limit, selections):
    """Report v5 gates separately from observed exact-head v8 runs (not a merge decision)."""
    fields = ()
    if selections:
        fields = tuple(field.strip() for field in selections[0].split(","))
        if (
            len(selections) != 1
            or len(set(fields)) != len(fields)
            or any(key not in CHECK_ROW_FIELDS for key in fields)
        ):
            raise click.UsageError("Use --json once, with distinct fields from: " + ", ".join(CHECK_ROW_FIELDS))
    if fields and repo_name and ctx.obj["app"].repo and resolve_repo(repo_name) != resolve_repo(ctx.obj["app"].repo):
        raise click.UsageError("Conflicting global and PR checks repository targets.")
    with _service(ctx, repo_name) as svc:
        result = pr_evidence(svc, number, scan_limit)
    outcome = result["outcome"]
    code = {"observed_completed": 0, "failed_or_canceled": 1, "ci_gate_not_passed": 1, "pending": 8}.get(outcome, 3)
    if not fields:
        _show(ctx, result)
    else:
        rows = check_rows(result, fields)
        if rows is not None:
            _show(ctx, rows)
        if code:
            click.echo(f"PR checks: {outcome}. Omit --json for the full evidence report.", err=True)
    ctx.exit(code)


set_gc_help(pr_checks, gc_json_fields=list(CHECK_ROW_FIELDS))


@run.command("artifacts")
@click.argument("run_id")
@repo_option
@page_option
@limit_option
@click.option("-a", "--attempt", type=click.IntRange(1), help="Expected current attempt.")
@click.option("--commit", help="Expected full head commit SHA.")
@click.pass_context
def run_artifacts(ctx, repo_name, run_id, page, limit, attempt, commit):
    """List one bounded page of run artifacts, without any download URLs."""
    from ..services.actions_artifacts import ActionsArtifactService  # noqa: PLC0415

    with _service(ctx, repo_name) as svc:
        _show(ctx, ActionsArtifactService(svc).list(run_id, page, limit, attempt, commit))


@run.command("download")
@click.argument("run_id")
@repo_option
@click.option("--artifact-id", multiple=True, help="Select one exact artifact ID instead of --name.")
@click.option("--name", multiple=True, help="Select one unique, case-sensitive artifact name instead of --artifact-id.")
@click.option("-a", "--attempt", type=click.IntRange(1), required=True, help="Observed current attempt (only 1).")
@click.option("--commit", required=True, help="Expected full head commit SHA.")
@click.option(
    "-O",
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="New ZIP file under an existing safe local directory; never overwritten or extracted.",
)
@click.pass_context
def run_download(ctx, repo_name, run_id, artifact_id, name, attempt, commit, output):
    """Save one verified artifact ZIP, without extracting it."""
    from ..services.actions_artifacts import ActionsArtifactService  # noqa: PLC0415

    if len(artifact_id) + len(name) != 1:
        raise click.UsageError("Specify exactly one --artifact-id or --name, once.")
    with _service(ctx, repo_name) as svc:
        _show(
            ctx,
            ActionsArtifactService(svc).download(
                run_id, artifact_id[0] if artifact_id else None, attempt, commit, output, name=name[0] if name else None
            ),
        )
