from __future__ import annotations

import click

CAPABILITY_MESSAGES = {
    "PR_REVIEW_COMMENT": (
        "GitCode review API does not support comment reviews;"
        " the pull request comment was posted instead."
    ),
    "PR_REVIEW_REQUEST_CHANGES": (
        "GitCode review API does not support request-changes reviews;"
        " the pull request comment was posted instead."
    ),
    "ISSUE_DEVELOP_BASE": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_DEVELOP_NAME": "--base and --name are not supported by 'gc issue develop'",
    "ISSUE_STATUS_GH_SEMANTICS": "GitCode-limited approximation of gh issue status",
    "PR_STATUS_GH_SEMANTICS": (
        "GitCode API approximation -- user-specific filtering is not available"
    ),
}


def capability_message(feature: str) -> str:
    return CAPABILITY_MESSAGES[feature]


def unsupported(feature: str) -> click.ClickException:
    return click.ClickException(capability_message(feature))
