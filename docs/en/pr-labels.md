# PR label edits

`gc pr edit NUMBER --add-label "help wanted,bug" --remove-label "old"`
uses dedicated GitCode PR-label endpoints, not generic `labels` replacement
or the unsupported `unset_labels` field. Additions use POST with a JSON array;
removals use DELETE with one URL-encoded name. Removing the final label works
without sending an empty generic PATCH or replacing unrelated labels.

Comma-separated input is deduplicated. Empty segments, dot-only names, control
characters and overlapping add/remove requests fail before writes. A literal
comma inside an individual label name cannot be represented by this CLI syntax.
Existing additions and absent removals are successful no-ops.

The CLI checks PR number/id and label identities before editing. It confirms
requested membership, removal, and preservation of unrelated label identities
on the final readback, allowing additional concurrent labels. Edits combined
with people or milestone changes share that final confirmation snapshot. These
calls are not transactional: a later error can follow an earlier successful
mutation. The CLI reports uncertainty and never automatically repeats or rolls
back writes. Inspect the known PR before retrying. Server-side concurrent changes
can still occur after any readback.

## Verification boundary

Unit tests and strict credential-isolated HTTP contracts cover the documented
request shapes and failure paths. Fixtures are synthetic, not live recordings.
For separately authorized live acceptance, use a disposable PR with known label
IDs: add one label while preserving another; remove one and then the last label;
exercise spaces, Unicode and URL-significant characters; repeat no-op edits;
combine title/people/milestone changes; add an unrelated label concurrently; and
inject failure after the first of two deletions. Verify no repeated write, false
success, or lost unrelated label. Inspect remote state before retrying a failure.

This change does not establish PR milestone-clearing semantics or authorize live
destructive tests, approvals, release or deployment.
