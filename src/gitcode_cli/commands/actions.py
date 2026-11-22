"""Native GitCode Actions, with bounded reads and separate v5 PR gates."""

from __future__ import annotations

import json
from contextlib import closing, contextmanager
from typing import Any

import click

from .._redact import redact
from ..actions_client import ActionsClient
from ..adapters.action_checks import pr_evidence
from ..context import AppContext
from ..helptext import GCSectionCommand, GCSectionGroup
from ..repo import resolve_repo
from ..services.actions import ActionsService

repo_option = click.option("-R", "--repo", "repo_name", help="[HOST/]OWNER/REPO (defaults to origin).")
page_option = click.option("--page", type=click.IntRange(1), default=1, show_default=True)
limit_option = click.option("-L", "--limit", type=click.IntRange(1, 100), default=20, show_default=True)
offset_option = click.option("--offset", type=click.IntRange(0), default=0, show_default=True)


@contextmanager
def _service(ctx: click.Context, repo_name: str | None):
    app: AppContext = ctx.obj["app"]
    owner, repo = resolve_repo(repo_name or app.repo)
    with closing(ActionsClient(app.token)) as client:
        yield ActionsService(client, owner, repo)


def _show(ctx: click.Context, value: dict):
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


@click.group(cls=GCSectionGroup, short_help="Inspect GitCode Actions runs")
def run():
    """Inspect GitCode Actions runs, jobs and step logs."""


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


@click.group(cls=GCSectionGroup, short_help="List or dispatch GitCode workflows")
def workflow():
    """List or explicitly dispatch GitCode workflows."""


@workflow.command("list")
@repo_option
@page_option
@limit_option
@click.pass_context
def workflow_list(ctx, repo_name, page, limit):
    """List one page of workflow definitions, not runs."""
    with _service(ctx, repo_name) as svc:
        _show(ctx, svc.page("workflows", page, limit))


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
@click.pass_context
def pr_checks(ctx, number, repo_name, scan_limit):
    """Report v5 gates separately from observed exact-head v8 runs (not a merge decision)."""
    with _service(ctx, repo_name) as svc:
        result = pr_evidence(svc, number, scan_limit)
    _show(ctx, result)
    ctx.exit(
        {"observed_completed": 0, "failed_or_canceled": 1, "ci_gate_not_passed": 1, "pending": 8}.get(
            result["outcome"], 3
        )
    )
