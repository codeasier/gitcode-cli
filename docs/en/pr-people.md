# Pull request people

GitCode has two different PR roles. `pr create -a/--assignee` and `pr edit --add-assignee/--remove-assignee` manage native **assignees (审查人)**. `pr create -r/--reviewer` and the corresponding edit flags manage **approval reviewers (评审人)**, read from `approval_reviewers`. These are not interchangeable and assignment is not approval.

Use account logins, comma-separated values, repeated create flags, or `@me`. Display names, teams and URLs are not supported. Conflicting addition/removal of the same account in the same role is rejected before writing. A dry run reports intended `people_operations`; it does not pretend the generic PR-create endpoint will apply those fields.

Creation first creates the PR once, then verifies its number/identity and role lists before calling the role endpoints. Edit performs this preflight before any update; a people-only edit never sends an empty generic PATCH. Already-present additions and already-absent removals are read-only no-ops. Reviewer additions use `add: true`, not replacement. Readback checks requested membership, stable PR/member identities, and preservation of unrelated people visible in preflight; concurrent extra additions are allowed.

These are separate, non-atomic API operations. Failure or unverifiable readback exits nonzero and identifies the PR as potentially created/partially updated. No create, role write or rollback is automatically repeated. Inspect that PR before retrying; a failed command does not mean creation was rolled back. Repository policy, permissions and concurrent removals can still prevent confirmation.

## API contract and validation

- [Assign native assignees](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-assignees/): POST `/pulls/{number}/assignees`, JSON comma-separated `assignees`.
- [Remove native assignees](https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-number-assignees/): DELETE the same path, **query** `assignees`, not JSON.
- [Assign approval reviewers](https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-pulls-number-approval-reviewers/): POST `/pulls/{number}/reviewers`, JSON `reviewers` and boolean `add: true`.
- [Remove approval reviewers](https://docs.gitcode.com/docs/apis/delete-api-v-5-repos-owner-repo-pulls-number-approval-reviewers/): DELETE the same path with JSON `reviewers`.
- [Read PR](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-pulls-number/): confirm `number`, `id`, `assignees` and `approval_reviewers`.

The source-linked fixture and strict `.invalid` RESPX contracts check serialized method/path/query/JSON and the no-repeat error paths without real credentials. CLI CI and MCP checkout compatibility are required; this is not live permission acceptance. A later authorized sandbox check should use dedicated accounts, retain a pre-existing person in each role, exercise add/remove/`@me` and permission failures, inspect readback, and clean only its own fixtures. No approval, merge, production-state change or additional credentials are implied.
