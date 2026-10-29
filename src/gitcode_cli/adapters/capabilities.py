from __future__ import annotations

import click

CAPABILITY_MESSAGES = {
    "ISSUE_CLOSE_REASON": (
        "gc currently does not support 'issue close --reason': no verified GitCode API contract for closing reasons. "
        "No request was sent; omit --reason to close without recording a reason."
    ),
    "ISSUE_COMMENT_LAST_NOT_FOUND": "No editable issue comment from the current user was found.",
    "ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE": (
        "Unable to verify the current user's issue comments on GitCode; refusing to edit or delete comments safely."
    ),
    "ISSUE_CREATE_IF_NONE_REQUIRES_EDIT_LAST": "--create-if-none can only be used together with --edit-last.",
    "ISSUE_DEVELOP_BASE": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_DEVELOP_NAME": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_LIST_APP": "GitCode issue API does not support --app filtering.",
    "ISSUE_STATUS_GH_SEMANTICS": (
        "GitCode-limited approximation of gh issue status: assigned and opened issues use user-level "
        "GitCode results; mentioned issues use repository mention filtering."
    ),
    "PR_MERGE_AUTHOR_EMAIL": "GitCode merge API does not support --author-email.",
    "PR_COMMENT_OWNERSHIP_UNVERIFIABLE": (
        "Unable to verify the current user's pull request comments on GitCode; refusing to edit or delete comments."
    ),
    "PR_MERGE_AUTO": "GitCode merge API does not support --auto.",
    "PR_EDIT_BASE": (
        "GitCode's pull request update API does not support changing the base branch; "
        "-B/--base cannot be used with 'gc pr edit'."
    ),
    "PR_EDIT_REMOVE_MILESTONE": (
        "gc currently does not support 'pr edit --remove-milestone': "
        "no verified GitCode API contract for clearing a PR milestone. "
        "No request was sent; omit --remove-milestone to edit other fields."
    ),
    "PR_REVIEW_REQUEST_CHANGES": (
        "GitCode review API does not support request-changes reviews; the pull request comment was posted instead."
    ),
    "PR_STATUS_GH_SEMANTICS": ("GitCode API approximation -- user-specific filtering is not available"),
    "REPO_CREATE_INTERNAL": "GitCode repositories are either public or private; --internal is not supported.",
    "REPO_FORK_DEFAULT_BRANCH_ONLY": (
        "GitCode fork API always copies every branch from the upstream repository; "
        "--default-branch-only is not supported."
    ),
    "REPO_FORK_NAME": "GitCode fork API does not support renaming the fork; --fork-name cannot be used.",
}


def capability_message(feature: str) -> str:
    return CAPABILITY_MESSAGES[feature]


def unsupported(feature: str) -> click.ClickException:
    return click.ClickException(capability_message(feature))
