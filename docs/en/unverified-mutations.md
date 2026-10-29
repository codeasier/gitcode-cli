# Mutation flags without a verified contract

Two recognized options currently fail closed in `gc`:

- `gc issue close --reason ...`: the [documented Issue update body](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-issues-number/) has no closing-reason field. Sending `state_reason` is not evidence that the provider records it.
- `gc pr edit --remove-milestone`: the [documented PR update body](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-number/) exposes an integer `milestone_number`, but provides no verified clearing convention. `gc` does not guess `0`, `null`, or an empty string.

Both the command and directly invoked adapter reject these options before any request. Combining them with comments, duplicate notices, title edits, labels, people, or other milestone options does not perform a partial edit. The options remain visible in help and are marked currently unsupported in the compatibility registry.

This describes a current CLI validation gap, **not** a claim that the platform can never support these actions. Support can be added after establishing a reliable contract and appropriate acceptance evidence.

Omit `--reason` to close normally without recording a reason; ordinary close/comment/idempotency behavior remains unchanged. Omit `--remove-milestone` to edit other PR fields; setting a positive milestone number or resolving a milestone title remains supported with readback. Existing people, labels and `@me` behavior is unchanged. Issue milestone removal is outside this change.

Offline tests specify zero-request rejection, direct-adapter safety, help/registry consistency and preserved supported operations. Strict `.invalid` routes and synthetic credentials are not live provider acceptance. Documentation was checked on 2026-10-29; no live mutation or credential change is required by this repair.
