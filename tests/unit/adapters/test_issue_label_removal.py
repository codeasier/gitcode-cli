"""Issue edits that must not send GitCode's ineffective labels=\"\" payload."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import click
import pytest

from gitcode_cli.adapters.issues import IssueAdapter
from gitcode_cli.errors import APIError, NetworkError
from gitcode_cli.services.issues import IssueService


def _edit(service, **overrides):
    options = {
        "title": None,
        "body": None,
        "add_assignee": None,
        "add_labels": None,
        "remove_assignee": None,
        "remove_labels": ("bug",),
        "milestone": None,
        "remove_milestone": False,
    }
    return IssueAdapter(service).edit_issue("owner", "repo", "42", **{**options, **overrides})


@pytest.fixture
def service():
    return MagicMock(spec=IssueService)


@pytest.mark.parametrize("labels", [[{"name": "bug"}], [{"title": "bug"}], ["bug"], "bug"])
def test_last_label_uses_delete_and_returns_readback(service, labels):
    after = {"number": "42", "labels": [], "html_url": "https://gitcode.invalid/issue/42"}
    service.get.side_effect = [{"labels": labels}, after]

    assert _edit(service) == after

    assert service.mock_calls == [
        call.get("owner", "repo", "42"),
        call.remove_label("owner", "repo", "42", "bug"),
        call.get("owner", "repo", "42"),
    ]


def test_removes_all_labels_once_and_preserves_concurrent_unrelated_label(service):
    after = {"labels": [{"name": "concurrent"}]}
    service.get.side_effect = [{"labels": ["bug", "docs", "bug"]}, after]

    assert _edit(service, remove_labels=(" bug ", "docs", "bug", "absent")) == after

    assert service.remove_label.call_args_list == [
        call("owner", "repo", "42", "bug"),
        call("owner", "repo", "42", "docs"),
    ]
    service.update.assert_not_called()


@pytest.mark.parametrize("labels", [[], ""])
def test_already_absent_removal_is_successful_noop(service, labels):
    current = {"number": "42", "labels": labels}
    service.get.return_value = current

    assert _edit(service) == current

    assert service.mock_calls == [call.get("owner", "repo", "42")]


def test_repeated_removal_does_not_repeat_delete(service):
    service.get.side_effect = [{"labels": ["bug"]}, {"labels": []}, {"labels": []}]

    assert _edit(service) == {"labels": []}
    assert _edit(service) == {"labels": []}

    service.remove_label.assert_called_once_with("owner", "repo", "42", "bug")
    service.update.assert_not_called()


@pytest.mark.parametrize(
    ("add_labels", "remove_labels", "expected"),
    [(None, ("bug",), "keep"), (("docs",), ("bug",), "keep,docs"), (("docs",), None, "keep,bug,docs")],
)
def test_nonempty_replacement_behavior_stays_unchanged(service, add_labels, remove_labels, expected):
    service.get.return_value = {"labels": ["keep", "bug"]}

    _edit(service, add_labels=add_labels, remove_labels=remove_labels)

    service.update.assert_called_once_with("owner", "repo", "42", labels=expected)
    service.remove_label.assert_not_called()


def test_remove_still_wins_when_the_same_label_is_also_added(service):
    service.get.side_effect = [{"labels": ["bug"]}, {"labels": []}]

    _edit(service, add_labels=("bug",))

    service.remove_label.assert_called_once_with("owner", "repo", "42", "bug")
    service.update.assert_not_called()


def test_mixed_fields_update_before_removal_without_empty_labels(service):
    before = {"labels": ["bug"], "assignee": "alice,bob"}
    after = {"labels": [], "title": "Updated", "assignee": "alice", "milestone": None}
    service.get.side_effect = [before, before, after]

    assert _edit(service, title="Updated", body="Body", remove_assignee="bob", remove_milestone=True) == after

    assert service.mock_calls == [
        call.get("owner", "repo", "42"),
        call.get("owner", "repo", "42"),
        call.update("owner", "repo", "42", title="Updated", body="Body", assignee="alice", milestone=0),
        call.remove_label("owner", "repo", "42", "bug"),
        call.get("owner", "repo", "42"),
    ]


def test_absent_label_does_not_suppress_other_edits(service):
    service.get.return_value = {"labels": []}
    service.update.return_value = {"labels": [], "body": "Updated"}

    assert _edit(service, body="Updated") == service.update.return_value

    service.update.assert_called_once_with("owner", "repo", "42", body="Updated")
    service.remove_label.assert_not_called()


@pytest.mark.parametrize("current", [None, {}, {"labels": None}, {"labels": {}}, {"labels": [{}]}, {"labels": [""]}])
def test_incomplete_snapshot_fails_before_any_write(service, current):
    service.get.return_value = current

    with pytest.raises(click.ClickException, match="Cannot safely remove labels"):
        _edit(service, body="Must not update")

    service.update.assert_not_called()
    service.remove_label.assert_not_called()


@pytest.mark.parametrize("name", [".", "..", "bug,docs"])
def test_invalid_delete_target_is_rejected_before_other_mutations(service, name):
    service.get.return_value = {"labels": [name]}

    with pytest.raises(click.ClickException, match="individual names"):
        _edit(service, body="Must not update", remove_labels=(name,))

    service.update.assert_not_called()
    service.remove_label.assert_not_called()


@pytest.mark.parametrize("error", [APIError("Denied", 403), NetworkError("Timeout")])
def test_failed_field_update_does_not_start_deletions(service, error):
    service.get.return_value = {"labels": ["bug"]}
    service.update.side_effect = error

    with pytest.raises(click.ClickException, match="field update completed=False.*0 label.*field update failed"):
        _edit(service, body="Updated")

    service.update.assert_called_once()
    service.remove_label.assert_not_called()
    service.get.assert_called_once()


@pytest.mark.parametrize("error", [APIError("Denied", 403), NetworkError("Timeout")])
def test_partial_delete_failure_reports_completed_steps_and_stops(service, error):
    service.get.return_value = {"labels": ["bug", "docs", "later"]}
    service.remove_label.side_effect = [None, error]

    with pytest.raises(
        click.ClickException, match="field update completed=True.*1 label.*label deletion failed"
    ) as exc:
        _edit(service, body="Updated", remove_labels=("bug", "docs", "later"))

    assert "may have taken effect" in str(exc.value)
    assert "no automatic retry or rollback" in str(exc.value)
    service.update.assert_called_once()
    assert service.remove_label.call_args_list == [
        call("owner", "repo", "42", "bug"),
        call("owner", "repo", "42", "docs"),
    ]
    service.get.assert_called_once()


@pytest.mark.parametrize(
    "readback",
    [None, {}, {"labels": None}, {"labels": [{}]}, {"labels": [3]}, {"labels": ["bug"]}, NetworkError("Timeout")],
)
def test_failed_or_unconfirmable_readback_never_reports_success_or_retries(service, readback):
    service.get.side_effect = [{"labels": ["bug"]}, readback]

    with pytest.raises(click.ClickException, match="1 label deletion request.*readback failed"):
        _edit(service)

    service.remove_label.assert_called_once()
    service.update.assert_not_called()
    assert service.get.call_count == 2
