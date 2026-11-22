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
fields. Array pagination is bounded; v8 envelope pagination, GitHub GraphQL,
custom hosts, arbitrary binary responses, and the `gh` proxy are not supported.
Use no credentials in request fields. An accepted or uncertain write is not
retried; verify the remote state before deciding to send it again. `--jq`
requires the jq executable on PATH.
