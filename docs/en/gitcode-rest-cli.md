# Direct GitCode REST command

Use the direct CLI, not the optional GitHub dispatcher:

```sh
gc -R OWNER/REPO api 'repos/{owner}/{repo}/issues' -X GET -F per_page=10
```

The URL is fixed to `https://api.gitcode.com`; the command uses documented
[GitCode REST](https://docs.gitcode.com/docs/apis/) PAT Bearer authentication.
HTTP redirects are not followed; JSON is the only data format. GitCode v5
documents Bearer usage; v8 route support here is an offline-tested URL and
protocol capability, not a guarantee that every endpoint accepts Bearer.
There is no fallback to a different token location after rejection.

Like `gh api`, fields or input make POST the default. Use `-X GET` for query
fields. Array pagination is bounded. Unrecognized object envelopes cannot be
paginated; GitHub GraphQL, custom hosts, arbitrary binary responses, and the
`gh` proxy are not supported.
Use no credentials in request fields. An accepted or uncertain write is not
retried; verify the remote state before deciding to send it again. `--jq`
requires the jq executable on PATH.


## Paginate the v8 workflow run list

```sh
gc api '/api/v8/repos/OWNER/REPO/actions/runs?branch=main&per_page=20' --paginate --slurp
```

The [documented v8 repository run listing](https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs/)
is the only object envelope that `gc api --paginate` accepts. Each validated,
redacted page is output as a JSON object; `--slurp` produces an array of those
objects, not a flattened list of runs. Use a literal OWNER/REPO path or supply
an explicit `-R OWNER/REPO` for placeholders; this mode does not infer an origin.
Any explicit repository must match the request's exact repository. The command starts at page 1,
holds filters and page size fixed (1–100; default 20), and accepts only
documented query parameters, uncompressed HTTP 200 responses, and JSON.
Conditional requests, redirects, and responses with a Content-Range or Link
header are refused. Numeric pagination headers, when present, must agree with
the requested page and the response body.

A changed total, partial page, missing or duplicate run ID, or response size/
page limit error stops pagination without emitting pages. Optional truncation
or incomplete-result indicators also cause an error unless explicitly false.
These checks detect some concurrent changes, but the provider does not offer
an atomic snapshot token; matching totals and unique IDs do not prove that
nothing changed.
