# Inspect a GitCode Actions failure

Definitions and executions have different identities: `gc workflow list` lists workflow
definitions, `gc run list` lists runs, and `gc run view` lists the jobs or steps within one
run. Output is JSON using GitCode field names. These commands do not translate the GitHub
Actions model, enable/disable workflows, or export complete job environments.

```console
gc workflow list -R owner/repo --page 1 --limit 20
gc workflow view ci.yml -R owner/repo
gc run list -R owner/repo --pr 42 --event MR
gc pr checks 42 -R owner/repo --scan-limit 100
gc run view RUN_ID -R owner/repo
gc run view RUN_ID -R owner/repo --with-steps --limit 10 --attempt 2 --commit FULL_SHA
gc run view RUN_ID -R owner/repo --job JOB_ID --attempt 2 --commit FULL_SHA
gc run view RUN_ID -R owner/repo --job JOB_ID --log --step STEP_ID --attempt 2 --commit FULL_SHA --offset 0 --limit 20
```

* For lists, use the returned `next_page` with the **same limit and filters**. Job/step lists
  use local windows because the v8 job endpoint does not support server-side pagination.
  Continue with `next_offset`; for logs use the returned offset and the same sort direction.
  The log POST is a read, not a trigger. Responses are capped at 2 MiB, individual log
  pages at 128 KiB; reduce the page size on overflow. A single oversized entry cannot be
  returned. Log text is JSON-escaped, not printed as terminal commands.
* For a script, `gc workflow list -R owner/repo --page 1 --limit 20 --json id,name,path,state`
  prints one array of definitions from the requested page, in server order. Select any subset
  of the four fields once. `id` is GitCode's **string** `workflow_id` (not a run ID);
  `path` is the listed `file_path`, not its YAML contents. Names and states are native
  strings. Unlike `gh workflow list`, this does not hide disabled workflows by default.
  Omit `--json` to see pagination metadata. The request and its authentication are
  unchanged; no extra pages or resources are read. If a selected value is missing,
  non-string, blank, or would be changed by credential redaction, no partial array is printed.
* `workflow view` finds exact IDs, names, filenames, or listed configuration paths.
  Exact IDs take precedence over names and filenames. It rejects ambiguous matches
  or an incomplete list, and returns only definition
  metadata, not YAML. The scan defaults to 100 definitions; use `--scan-limit` up to
  500 when needed. It does not claim a transactional snapshot.
* `--attempt` guards the **current** attempt; the documented detail endpoint has no
  historical-attempt selector. Except for the single-response `--with-steps` snapshot below,
  commit and attempt are checked before and after fetching
  jobs/logs. A race discards the result instead of attributing it to the old attempt.
* PR checks read the requested v5 PR's head and merge gates, separately inspect v8
  PR-number- and MR-event-filtered runs, then re-read the head. Within the bounded scan,
  the latest run number for each workflow is checked against its run detail. Missing
  evidence, a synthetic merge revision with no documented mapping to this PR head, a
  changed head, and a scan exceeding its cap are not green results. Permission failures
  and absent endpoints do not mean the repository has no runs. Before a possible exit 0,
  the command repeats the bounded v8 run list and current details and checks that run
  membership, exact head, attempt and status have not changed. Increasing the cap from
  its default 100 is not supported; use `run list --page` for deeper diagnosis.
* Exit status: **0** = both v8 snapshots show the same latest exact-head attempts
  as `COMPLETED`, and both v5 snapshots explicitly show an enabled and passed pipeline gate;
  **1** = observed failure/cancellation, enabled v5 pipeline gate that has not passed,
  or command/request error; **8** = pending/paused; **3** = unknown, unavailable, absent,
  incomplete, stale, or no verifiable pipeline gate. The separately reported v5
  `ci_state_passed` is **not** a v8 result. Exit 0 does not establish required-check
  coverage, permission to merge, or merge readiness. This is a bounded observation,
  not an atomic server snapshot.

## Select PR check fields

To print one row per observed workflow for a PR, use
`gc pr checks 42 -R owner/repo --json workflow,state,event`. Select any subset, once.
Fields come from the existing [run-detail snapshot](https://docs.gitcode.com/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/):
`workflow` is its name, `state` is the native run status, and `event` is `MR`.
Missing or non-string field values are null. These are not individual jobs or required
checks. There is no `bucket`: a `COMPLETED` run alone does not establish a pass.
The usual exit codes above still apply. Nonzero outcomes are named on stderr, even
when all displayed runs completed but the v5 gate failed. A complete empty result
prints `[]` (exit 3); stale, incomplete or inaccessible evidence prints no rows
(no stdout). Omit `--json` for the full report including gates and diagnostics.

## Inspect steps across jobs in one read

Use `--with-steps` to see which steps GitCode reported in each job without first
looking up every job ID. This direct `gc` mode uses only the documented
[run detail](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/).
The run ID, current attempt and full head SHA are checked against the same response
as the jobs. No separate job, log or workflow request is made. The default view
and the single-job `--job` view are unchanged.

The result contains `run` (ID, attempt and SHA), `jobs`, `total_count` (job records
in this response) and `next_offset`. Each job includes its enclosing `stage` and
`steps`. At all three levels only the native `id`, `name` and `status` strings are
shown. This is not GitHub's `--json jobs`: there is no inferred conclusion,
execution ID, retry selector, execution order or merge decision. For example,
`COMPLETED` is reported as-is, not as success. Stage-level pre/post hooks are not job steps.

`--offset` and `--limit` count jobs in returned array order across stages.
Use the returned offset with the same commit and attempt; the contents can still
change between reads. The entire response must fit the existing 2 MiB transport
cap. At most 100 steps **in total** may be shown on one page; an oversized page
fails without partial results. Lower the job limit, or use `--job JOB_ID` to page
through a single large job. The entire response hierarchy is validated, including
off-page rows. Stage IDs must be unique across stages, job IDs across the run,
and step IDs within each job. IDs use the native Actions resource ID grammar.
Missing/invalid metadata, including lone surrogates or terminal/format controls
in names, IDs or states, fails without emitting a partial result. Identity and
status are not rewritten to placeholders if they cannot be safely shown. Input,
environment, messages, logs and execution configuration are not exported.

## Watch one run without changing it

```console
gc run watch RUN_ID -R owner/repo
gc run watch RUN_ID -R owner/repo --interval 5 --timeout 600 --exit-status
```

Watch reads only the [run-detail GET](https://docs.gitcode.com/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/).
The first read pins the explicit ID, full head SHA and current attempt. A rerun before that
first read may already be the current attempt; a change during the watch stops it. Watch
does not select a run interactively, enumerate jobs/steps, support `--compact`, or route via
the `gh` proxy.

Changes between `RUNNING`, `PAUSED` and `SUSPEND` appear on stderr. A recognized terminal
state produces a single JSON object on stdout with `workflow_run_id`, `head_sha`, `attempt`
and `status`. Default exit 0 means **observed** `COMPLETED`, `FAILED` or `CANCELED`, not
that the run passed. With `--exit-status`, `FAILED` and `CANCELED` exit 1. `IGNORED` exits
3 in both modes: a skipped run is not a passing result. Even `COMPLETED` reports only
provider-level execution completion, **not** success of all jobs, PR required checks or
merge readiness.

`-i/--interval` waits 1–60 seconds between reads (default 3). `--timeout` is a monotonic
local deadline of 1–900 seconds (default 300), including any in-flight read. A timeout,
HTTP error, unknown or missing state, or unverifiable identity exits nonzero without a
terminal result. Ctrl-C exits 130. No late response is accepted. The watcher stops
admitting polls when it observes shutdown or expiry. A GET already admitted may still
unwind after local exit; neither timeout nor interruption sends a remote cancel.
Offline contracts use a synthetic transport; verification in an authorized GitCode
environment is still pending.

## Explicit writes

```console
gc workflow run ci.yml -R owner/repo --ref feature-branch -f suite=smoke
gc run rerun RUN_ID -R owner/repo --commit FULL_SHA --attempt 2 --job-run-id JOB_RUN_ID
gc run rerun RUN_ID -R owner/repo --commit FULL_SHA --attempt 2
gc run cancel RUN_ID -R owner/repo --commit FULL_SHA --attempt 2
```

* Dispatch needs an explicit branch/tag and a workflow ID or YAML filename. Inputs are literal
  strings (`name=value`, not shell expansion or files). Dispatch returns the upstream run ID.
* Writes need an authenticated session. Retry accepts explicit **job-run IDs** from
  failed jobs, not job IDs, step IDs, or names. It refuses to submit if the job list is
  incomplete or if a unique failed job's `exec_id` and its steps' `job_run_id` values
  do not agree. This conservative identity check may reject records without those fields.
  Repeat the option to select several. Omitting it requests a rerun of the **entire run**.
  The read-before-write commit/attempt guard is not an atomic precondition. GitCode's
  `success: true` acknowledges the request; it is not proof of a new attempt or of passing CI.
  Inspect runs and attempts afterward, especially after an error. Never resubmit automatically.
* Cancel prompts before networking (or pass `--yes`), requires authentication, and
  submits one native stop only for an exact run ID, current attempt, full commit SHA,
  and `RUNNING` status. An already `CANCELED` attempt does not get another stop. GitCode
  cannot atomically pin the attempt at stop time. Even `success: true` is not proof of
  cancellation: the command performs one read-back, and only a matching `CANCELED`
  result exits 0. A confirmed request without a canceled read-back exits 3; a
  rejected request or unavailable/changed read-back exits 1. Inspect before any retry.
* These are CLI capabilities, not new MCP tools. Offline contracts do not establish live
  access for every scope, account, or GitCode installation.

Sources: [v5 PR detail](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/),
[v8 runs](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs/),
[run detail](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/),
[jobs](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id-jobs/),
[job detail](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id-jobs-job-id/),
[step logs](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-jobs-job-id-logs/),
[workflows](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-workflows/),
[dispatch](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-workflows-workflow-id-dispatches/),
[retry](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-retry/),
[rerun](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-rerun/),
[stop](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-stop/).

See the [Actions artifact contract](actions-artifacts.md) for listing and bounded ZIP downloads.
