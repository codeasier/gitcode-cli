# Repository synchronization preflight

`gc repo sync OWNER/REPO` first reads the selected repository. An explicit
non-fork result fails with **not a fork** before the synchronization request,
instead of relying on the provider's opaque `Project not found:null` error.
Missing or ambiguous fork information fails separately as **cannot verify**;
strings, floats and arbitrary integers are not coerced into permission to sync.

The [official repository detail documentation](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo/)
(checked 2026-10-29) describes `fork` as an integer but shows a boolean concrete
example. This preflight accepts only boolean values or exact integer 0/1. A
confirmed fork continues through the existing single synchronization request;
no retries or new force/source/branch semantics are introduced.

Strict `.invalid` HTTP contracts and unit regressions cover non-fork, unknown,
failed lookup and successful preflight paths using synthetic credentials. They
are not live synchronization acceptance. In a separately authorized disposable
repository, verify a non-fork is rejected without a sync request, a known fork
continues, and unavailable metadata does not produce a write. Upstream selection,
server-side races and completion semantics remain those of the existing sync API.
