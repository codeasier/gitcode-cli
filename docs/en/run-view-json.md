# Read metadata for one current workflow run

`gc run view RUN -R OWNER/REPO --json workflowName,attempt,headSha` emits one JSON object, in the requested field order. Select any nonempty subset:

| Field | JSON type | [GitCode v8 run detail](https://docs.gitcode.com/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/) |
| --- | --- | --- |
| `attempt` | integer | `attempt`, as reported, including zero |
| `headSha` | string | `head_sha`, the full commit SHA |
| `workflowName` | string | `workflow_name`, not the run title or the YAML filename |

The command checks the requested run ID, full SHA and attempt in **one** current run detail response. To require specific values, add `--attempt N --commit FULL_SHA`. A different attempt or commit, incomplete identity, or missing selected workflow name exits nonzero without JSON. No jobs, workflow definitions or logs are fetched separately.

The names match [gh run view](https://cli.github.com/manual/gh_run_view) ([upstream field definitions](https://github.com/cli/cli/blob/v2.105.0/pkg/cmd/run/shared/shared.go)); historical attempt lookup, other gh output fields and gh-proxy routing are not provided by this selection. Omit `--json` to use the existing jobs, steps or logs modes. Their pagination and sorting flags do not apply to a single metadata object.
