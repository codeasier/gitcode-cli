from __future__ import annotations

import click

CAPABILITY_MESSAGES = {
    "ISSUE_COMMENT_LAST_NOT_FOUND": "No editable issue comment from the current user was found.",
    "ISSUE_COMMENT_OWNERSHIP_UNVERIFIABLE": (
        "Unable to verify the current user's issue comments on GitCode; refusing to edit or delete comments safely."
    ),
    "ISSUE_CREATE_IF_NONE_REQUIRES_EDIT_LAST": "--create-if-none can only be used together with --edit-last.",
    "ISSUE_DEVELOP_BASE": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_DEVELOP_NAME": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_LIST_APP": "GitCode issue API does not support --app filtering.",
    "ISSUE_STATUS_GH_SEMANTICS": "GitCode-limited approximation of gh issue status",
    "PR_MERGE_AUTHOR_EMAIL": "GitCode merge API does not support --author-email.",
    "PR_MERGE_AUTO": "GitCode merge API does not support --auto.",
    "PR_REVIEW_REQUEST_CHANGES": (
        "GitCode review API does not support request-changes reviews; the pull request comment was posted instead."
    ),
    "PR_STATUS_GH_SEMANTICS": ("GitCode API approximation -- user-specific filtering is not available"),
}


def capability_message(feature: str) -> str:
    return CAPABILITY_MESSAGES[feature]


def unsupported(feature: str) -> click.ClickException:
    return click.ClickException(capability_message(feature))
