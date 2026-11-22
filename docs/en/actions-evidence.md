# Inspect a GitCode Actions failure

Definitions and executions have different identities: `gc workflow list` lists workflow
definitions, `gc run list` lists runs, and `gc run view` lists the jobs or steps within one
run. Output is JSON using GitCode field names. These commands do not translate the GitHub
Actions model, enable/disable workflows, or export complete job environments.

```console
gc workflow list -R owner/repo --page 1 --limit 20
gc run list -R owner/repo --pr 42 --event MR
gc pr checks 42 -R owner/repo --scan-limit 100
gc run view RUN_ID -R owner/repo
gc run view RUN_ID -R owner/repo --job JOB_ID --attempt 2 --commit FULL_SHA
gc run view RUN_ID -R owner/repo --job JOB_ID --log --step STEP_ID --attempt 2 --commit FULL_SHA --offset 0 --limit 20
```

* For lists, use the returned `next_page` with the **same limit and filters**. Job/step lists
  use local windows because the v8 job endpoint does not support server-side pagination.
  Continue with `next_offset`; for logs use the returned offset and the same sort direction.
  The log POST is a read, not a trigger. Responses are capped at 2 MiB, individual log
  pages at 128 KiB; reduce the page size on overflow. A single oversized entry cannot be
  returned. Log text is JSON-escaped, not printed as terminal commands.
* `--attempt` guards the **current** attempt; the documented detail endpoint has no
  historical-attempt selector. Commit and attempt are checked before and after fetching
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

## Explicit writes

```console
gc workflow run ci.yml -R owner/repo --ref feature-branch -f suite=smoke
gc run rerun RUN_ID -R owner/repo --commit FULL_SHA --attempt 2 --job-run-id JOB_RUN_ID
gc run rerun RUN_ID -R owner/repo --commit FULL_SHA --attempt 2
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
[rerun](https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-rerun/).
