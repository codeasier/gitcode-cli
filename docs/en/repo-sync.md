# Synchronize one fork branch

`gc repo sync OWNER/FORK --branch release/1` asks GitCode to sync the fork's
`release/1` branch from its upstream. With no `--branch`, gc resolves the
parent's default branch, **not the fork's default**. If the parent or branch
cannot be identified, specify `--branch` explicitly. gc never omits the branch
from a CLI synchronization request: [GitCode documents that doing so updates
all branches](https://docs.gitcode.com/en/docs/apis/put-api-v-5-repos-owner-repo-sync-repo/).

Before sending the write, gc reads the destination's
[repository metadata](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/).
It accepts only a boolean or exact integer 0/1 for `fork`. A non-fork or
ambiguous value fails before synchronization. gc submits one sync request
and requires the documented boolean `repo_sync_result=true` before reporting
success. If the outcome is unclear, inspect the fork before retrying.

This is the provider's remote fork-sync operation, not a local Git update.
Arbitrary sources, forced resets and guarantees of GitHub-identical behavior
on divergence are not supported. Offline tests use synthetic fork metadata
and exercise the exact branch body; they do not establish live acceptance.

## Read status without synchronizing

`gc repo sync-status OWNER/FORK -b release/1` reads GitCode's
[fork synchronization status](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-sync-repo/)
with **one GET**. Sign in first. Supply the literal owner/fork and one short
branch name, not a URL, `-R`, or `refs/heads/…`. There is no origin or default
branch lookup, redirect, retry, or fallback to the PUT above.

The JSON result preserves GitCode's boolean `repo_sync_result` and string
`repo_sync_message`. Either boolean is a successful *read*: neither proves
commit ancestry or an ahead/behind count. Control characters, long messages,
and messages resembling credentials or links are withheld. Malformed data
fails without partial output. This is a native `gc` command, not a `gh`
or MCP interface. The request contract is tested offline, not against a live fork.
