"""Unverified mutation flags fail before any adapter-side effect."""

from unittest.mock import MagicMock, call

import click
import pytest

from gitcode_cli.adapters.capabilities import CAPABILITY_MESSAGES
from gitcode_cli.adapters.issues import IssueAdapter
from gitcode_cli.adapters.pulls import PullRequestAdapter


@pytest.mark.parametrize("reason", ["completed", "not_planned", "not planned", "", "future-value"])
@pytest.mark.parametrize("state", ["open", "closed"])
def test_close_reason_is_rejected_before_read_comment_or_update(reason, state):
    service = MagicMock()
    service.get.return_value = {"state": state, "title": "Existing"}
    with pytest.raises(click.ClickException) as error:
        IssueAdapter(service).close_issue("owner", "repo", "42", comment="Do not post", reason=reason)
    assert str(error.value) == CAPABILITY_MESSAGES["ISSUE_CLOSE_REASON"]
    assert not service.mock_calls


@pytest.mark.parametrize("state", ["open", "closed"])
@pytest.mark.parametrize("comment", [None, "Done"])
def test_close_without_reason_preserves_existing_semantics(state, comment):
    service = MagicMock()
    service.get.return_value = {"state": state, "title": "Existing"}
    result = IssueAdapter(service).close_issue("owner", "repo", "42", comment=comment, reason=None)
    expected = [call.get("owner", "repo", "42")]
    if comment:
        expected.append(call.comment("owner", "repo", "42", comment))
    if state == "open":
        expected.append(call.update("owner", "repo", "42", state="close", title="Existing"))
        assert result.message == "closed"
    else:
        assert result.message == ("already_closed_commented" if comment else "already_closed")
    assert service.mock_calls == expected


def edit(adapter, **overrides):
    options = dict.fromkeys(
        (
            "title",
            "body",
            "add_assignee",
            "add_label",
            "add_reviewer",
            "remove_assignee",
            "remove_label",
            "remove_reviewer",
            "milestone",
        )
    )
    options.update({"remove_milestone": False, **overrides})
    return adapter.edit_pr("owner", "repo", 42, **options)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"title": "Do not update"},
        {"milestone": "needs a lookup"},
        {"add_assignee": "@me", "add_reviewer": "@me"},
        {"add_label": "new", "remove_label": "old"},
    ],
)
def test_remove_milestone_fails_before_lookup_or_any_other_change(overrides):
    service, users, milestones = MagicMock(), MagicMock(), MagicMock()
    adapter = PullRequestAdapter(service, users, milestone_service=milestones)
    with pytest.raises(click.ClickException) as error:
        edit(adapter, remove_milestone=True, **overrides)
    assert str(error.value) == CAPABILITY_MESSAGES["PR_EDIT_REMOVE_MILESTONE"]
    assert not service.mock_calls and not users.mock_calls and not milestones.mock_calls


def test_setting_milestone_keeps_verified_number_and_confirmation():
    service = MagicMock()
    service.get.return_value = {"number": 42, "milestone": {"number": 7}}
    result = edit(PullRequestAdapter(service), milestone="7", title="New title")
    assert result == {"number": 42, "milestone": {"number": 7}}
    assert service.mock_calls == [
        call.update("owner", "repo", 42, title="New title", milestone_number=7),
        call.get("owner", "repo", 42),
    ]
