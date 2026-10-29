# Issue and pull request JSON output

Create, list and view use the same response-based projection for structured
output. Numeric repository-local `number` values become integers (never the
global `id`); unknown or malformed values remain null. State is uppercase, with
`OPENED` normalized to `OPEN`. `url` prefers the server's `html_url`, then
`web_url`, then an already-web `url`; an API URL is not emitted as the canonical
web URL. `createdAt` and `updatedAt` also accept their snake-case response aliases.

For PR creation responses, `source_branch` / `target_branch` supply the branch
names and minimal `head` / `base` objects when needed. No repository object or
commit SHA is invented. Existing nested response fields are retained. Boolean
`draft` is preferred; `work_in_progress` accepts only a boolean or integer 0/1,
not truthy strings. A missing body can use the response's `description`.

The raw response aliases remain available alongside the canonical fields. The
projection never takes state, draft, refs or milestone values from CLI request
options. Ordinary human output and dry-run payloads do not use this projection.

## Create readback and partial success

When a requested supported JSON field is absent from a successful create
response, one GET may retrieve the created object using its server-returned
positive number. An arbitrary unknown field does not cause a GET. `--jq` operates
on the full object, so its readback decision uses the documented create fields
rather than attempting to parse the expression. A milestone-setting PR readback
already performed by the adapter is reused instead of issuing another GET.

The GET response is the authoritative output snapshot. Null or still-missing
fields are not replaced with request values, and there is no repeated GET. If
GET fails, returns invalid JSON, a non-object, or a different number, the CLI
reports the create response's number and that its output could not be read. Inspect
the reported object before retrying: creation is never automatically repeated
or rolled back. A missing trustworthy number is not replaced by a title search
or a guess about the latest object.

## Repository paths

`repo list/view --json nameWithOwner` uses canonical repository/namespace paths,
not display names with whitespace removed. `path_with_namespace` is preferred,
followed by namespace/owner path plus repository path, then a valid `full_name`.
Display `name` is unchanged. Insufficient canonical path evidence yields null.

Offline tests validate serialization and projection, not live GitCode account
permissions, repository policy, or deployment behavior.
