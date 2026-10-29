"""Setting-only milestone resolution; legacy clearing and people stay unchanged."""

from unittest.mock import MagicMock, call

import click
import pytest

from gitcode_cli.adapters._milestones import milestone_number, resolve_pr_milestone
from gitcode_cli.adapters.pulls import PullRequestAdapter
from gitcode_cli.errors import APIError, NetworkError


def _create(adapter, milestone="7", dry_run=False):
    return adapter.create_pr(
        "owner",
        "repo",
        title="Title",
        body="Body",
        base="main",
        head="feature",
        draft=False,
        milestone=milestone,
        labels=None,
        reviewers=None,
        assignees=None,
        dry_run=dry_run,
    )


def _edit(adapter, milestone="7", remove=False):
    return adapter.edit_pr(
        "owner",
        "repo",
        42,
        title=None,
        body=None,
        add_assignee=None,
        add_label=None,
        add_reviewer=None,
        remove_assignee=None,
        remove_label=None,
        remove_reviewer=None,
        milestone=milestone,
        remove_milestone=remove,
    )


@pytest.mark.parametrize(
    "value,expected",
    [(1, 1), ("007", 7), (True, None), (0, None), ("0", None), (-1, None), ("１", None), (None, None), (1.5, None)],
)
def test_number_validation(value, expected):
    assert milestone_number(value) == expected


def test_numeric_and_absent_input_need_no_lookup():
    assert resolve_pr_milestone(None, "owner", "repo", "007") == 7
    assert resolve_pr_milestone(None, "owner", "repo", None) is None
    for value in ("", " ", "0"):
        with pytest.raises(click.UsageError):
            resolve_pr_milestone(None, "owner", "repo", value)
    with pytest.raises(click.ClickException, match="lookup is unavailable"):
        resolve_pr_milestone(None, "owner", "repo", "v1")


def test_title_match_on_later_page_and_all_states():
    service = MagicMock()
    service.list_milestones.side_effect = [
        [{"number": n, "title": f"release {n}"} for n in range(1, 101)],
        [{"number": "101", "title": "v1"}],
    ]
    assert resolve_pr_milestone(service, "owner", "repo", "v1") == 101
    assert service.list_milestones.call_args_list == [
        call("owner", "repo", state="all", page=1, per_page=100),
        call("owner", "repo", state="all", page=2, per_page=100),
    ]


@pytest.mark.parametrize(
    "items",
    [
        None,
        {},
        [None],
        [{"number": True, "title": "v1"}],
        [{"number": 1}],
        [{"number": 1, "title": "other"}],
        [{"number": 1, "title": "v1"}, {"number": 2, "title": "v1"}],
        [{"number": 1, "title": "v1"}, {"number": 1, "title": "other"}],
    ],
)
def test_unknown_or_ambiguous_title_prevents_create_and_edit(items):
    service, milestones = MagicMock(), MagicMock()
    milestones.list_milestones.return_value = items
    adapter = PullRequestAdapter(service, milestone_service=milestones)
    for operation in (_create, _edit):
        with pytest.raises(click.ClickException, match="no PR write was attempted"):
            operation(adapter, "v1")
    service.create.assert_not_called()
    service.update.assert_not_called()


def test_lookup_error_prevents_write():
    service, milestones = MagicMock(), MagicMock()
    milestones.list_milestones.side_effect = APIError("Synthetic rejection", 403)
    with pytest.raises(APIError):
        _create(PullRequestAdapter(service, milestone_service=milestones), "v1")
    service.create.assert_not_called()


def test_matching_first_page_does_not_hide_later_duplicate_or_repeated_page():
    service = MagicMock()
    first = [{"number": n, "title": "v1" if n == 1 else str(n)} for n in range(1, 101)]
    for last in ([{"number": 101, "title": "v1"}], first):
        service.list_milestones.side_effect = [first, last]
        with pytest.raises(click.ClickException):
            resolve_pr_milestone(service, "owner", "repo", "v1")


def test_lookup_bound_refuses_incomplete_collection():
    service = MagicMock()
    service.list_milestones.side_effect = [
        [{"number": page * 100 + n, "title": str(n)} for n in range(1, 101)] for page in range(100)
    ]
    with pytest.raises(click.ClickException, match="pagination limit"):
        resolve_pr_milestone(service, "owner", "repo", "v1")
    assert service.list_milestones.call_count == 100


@pytest.mark.parametrize("operation", [_create, _edit])
def test_set_uses_number_and_confirms_once(operation):
    service = MagicMock()
    service.create.return_value = {"number": "42"}
    service.get.return_value = {"number": 42, "milestone": {"number": "7"}}
    result = operation(PullRequestAdapter(service))
    item = result.item if operation is _create else result
    assert item == service.get.return_value
    write = service.create if operation is _create else service.update
    assert write.call_count == 1
    assert write.call_args.kwargs["milestone_number"] == 7
    assert "milestone" not in write.call_args.kwargs
    service.get.assert_called_once_with("owner", "repo", 42)


@pytest.mark.parametrize(
    "readback",
    [
        None,
        {},
        {"milestone": None},
        {"milestone": {"number": True}},
        {"milestone": {"number": 8}},
        {"number": 43, "milestone": {"number": 7}},
        {"number": True, "milestone": {"number": 7}},
        {"milestone": {"number": 7}},
        NetworkError("Synthetic timeout"),
    ],
)
@pytest.mark.parametrize("operation", [_create, _edit])
def test_unconfirmed_write_is_partial_success_and_never_repeated(readback, operation):
    service = MagicMock()
    service.create.return_value = {"number": 42}
    if isinstance(readback, Exception):
        service.get.side_effect = readback
    else:
        service.get.return_value = readback
    with pytest.raises(click.ClickException, match="PR #42 may have been created or updated"):
        operation(PullRequestAdapter(service))
    write = service.create if operation is _create else service.update
    assert write.call_count == 1
    service.get.assert_called_once()


@pytest.mark.parametrize("item", [None, {}, {"number": True}])
def test_created_number_missing_does_not_repeat_post(item):
    service = MagicMock()
    service.create.return_value = item
    with pytest.raises(click.ClickException, match="creation may have succeeded"):
        _create(PullRequestAdapter(service))
    service.create.assert_called_once()
    service.get.assert_not_called()


def test_dry_run_and_unchanged_legacy_removal():
    service, milestones = MagicMock(), MagicMock()
    milestones.list_milestones.return_value = [{"number": 7, "title": "v1"}]
    adapter = PullRequestAdapter(service, milestone_service=milestones)
    assert _create(adapter, "v1", dry_run=True).item["milestone_number"] == 7
    service.create.assert_not_called()
    service.get.assert_not_called()
    milestones.reset_mock()
    _edit(adapter, "v1", remove=True)
    service.update.assert_called_once_with("owner", "repo", 42, milestone="")
    milestones.list_milestones.assert_not_called()
    service.get.assert_not_called()
