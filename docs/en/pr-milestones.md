# Pull request milestone setting

`gc pr create --milestone VALUE` and `gc pr edit NUMBER --milestone VALUE`
accept a positive numeric milestone number or an exact milestone title. The
adapter sends the documented integer `milestone_number` field, not `milestone`.

Title lookup reuses the Issue service's repository milestone listing. It reads
all pages (bounded to 100 pages), requires one exact title match, and refuses
missing, ambiguous, repeated or malformed evidence before a PR write. Numeric
input does not require title lookup. Zero is not treated as a clearing operation.

`pr create --dry-run --milestone TITLE` can make read-only milestone-list
requests to resolve the title. It prints the resolved payload and does not create
a PR. Numeric dry-run input requires no provider request.

After a create/edit with a requested milestone, the CLI reads the PR once and
checks the returned milestone number before reporting success. If that read
fails or the milestone is absent/different, the mutation may already have
completed. The error identifies the PR number when available; verify its state
before retrying. There is no automatic repeat, rollback or second PR creation.

## Related behavior and validation boundaries

- `pr edit --remove-milestone` currently fails before any request because no
  clearing contract has been verified; see [unverified mutations](unverified-mutations.md).
  Neither zero nor null is introduced as a guessed sentinel.
- Assignees and approval reviewers use distinct native role endpoints and
  readback checks; see [PR people](pr-people.md). Assignment is not approval.
- Offline tests are not evidence of live GitCode acceptance or permissions.

Public contracts checked on 2026-10-29:
[create PR](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls/),
[update PR](https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-number/),
[get PR](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/),
and [repository milestones](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-milestones/).
