"""No-network role planning, partial-success and readback regressions."""

from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.adapters._pr_people import resolve_people
from gitcode_cli.adapters.pulls import PullRequestAdapter
from gitcode_cli.errors import APIError, NetworkError


def person(login):
    return {"login": login, "id": "id-" + login}


def item(assigned=(), reviewed=(), **overrides):
    return {
        "number": 42,
        "id": 1042,
        "assignees": [person(login) for login in assigned],
        "approval_reviewers": [person(login) for login in reviewed],
        **overrides,
    }


def create(adapter, **overrides):
    options = {
        "title": "Title",
        "body": "Body",
        "base": "main",
        "head": "feature",
        "draft": False,
        "milestone": None,
        "labels": None,
        "reviewers": (),
        "assignees": ("alice",),
        "dry_run": False,
    }
    return adapter.create_pr("owner", "repo", **{**options, **overrides})


def edit(adapter, **overrides):
    options = {
        "title": None,
        "body": None,
        "add_assignee": "alice",
        "add_label": None,
        "add_reviewer": None,
        "remove_assignee": None,
        "remove_label": None,
        "remove_reviewer": None,
        "milestone": None,
        "remove_milestone": False,
    }
    return adapter.edit_pr("owner", "repo", 42, **{**options, **overrides})


def test_resolve_comma_repeatable_duplicate_and_current_user():
    users = MagicMock()
    users.current.return_value = {"login": "alice"}
    assert resolve_people(("bob, @me", "alice", "@me"), users) == ("bob", "alice")
    users.current.assert_called_once_with()


@pytest.mark.parametrize("value", ["", " ", "a,,b", "@all", "org/team", "bad name", "a\x00b", "http:alice"])
def test_invalid_people_fail_before_create(value):
    service = MagicMock()
    with pytest.raises(click.ClickException):
        create(PullRequestAdapter(service), assignees=(value,))
    service.create.assert_not_called()
    service.get.assert_not_called()


@pytest.mark.parametrize("current", [None, [], {}, {"login": ""}, {"login": "@me"}])
def test_invalid_current_user_fails_before_write(current):
    service, users = MagicMock(), MagicMock()
    users.current.return_value = current
    with pytest.raises(click.ClickException):
        create(PullRequestAdapter(service, users), reviewers=("@me",))
    service.create.assert_not_called()


def test_current_user_requires_lookup_service():
    with pytest.raises(click.ClickException, match="lookup is unavailable"):
        resolve_people(("@me",), None)


def test_conflicting_role_change_fails_before_any_pr_call():
    service = MagicMock()
    with pytest.raises(click.UsageError, match="same account"):
        edit(PullRequestAdapter(service), remove_assignee="alice")
    assert not service.mock_calls


def test_create_separates_roles_from_create_and_preserves_other_people():
    service = MagicMock()
    service.create.return_value = {"number": "42"}
    service.get.side_effect = [
        item(("existing",), ("existing-reviewer",)),
        item(("existing", "alice"), ("existing-reviewer", "bob")),
    ]
    result = create(PullRequestAdapter(service), reviewers=("bob",))
    payload = service.create.call_args.kwargs
    assert "assignees" not in payload and "reviewers" not in payload
    service.create.assert_called_once()
    service.add_assignees.assert_called_once_with("owner", "repo", 42, "alice")
    service.add_reviewers.assert_called_once_with("owner", "repo", 42, "bob")
    assert result.item == item(("existing", "alice"), ("existing-reviewer", "bob"))


@pytest.mark.parametrize("identity", [1042, "1042"])
def test_create_identity_is_bound_to_first_readback(identity):
    service = MagicMock()
    service.create.return_value = {"number": 42, "id": identity}
    service.get.side_effect = [item(), item(("alice",))]
    assert create(PullRequestAdapter(service)).item == item(("alice",))
    service.create.assert_called_once()
    service.add_assignees.assert_called_once()


@pytest.mark.parametrize("identity", [2042, None, True, 0, -1, "", "bad", 1042.0])
def test_invalid_or_conflicting_creation_identity_stops_before_people_writes(identity):
    service = MagicMock()
    service.create.return_value = {"number": 42, "id": identity}
    service.get.return_value = item()
    with pytest.raises(click.ClickException, match="creation identity was not confirmed"):
        create(PullRequestAdapter(service), reviewers=("bob",))
    service.create.assert_called_once()
    service.get.assert_called_once()
    for method in ("add_assignees", "remove_assignees", "add_reviewers", "remove_reviewers"):
        getattr(service, method).assert_not_called()


def test_people_only_edit_never_calls_generic_patch():
    service = MagicMock()
    service.get.side_effect = [item(("keep", "remove"), ("old",)), item(("keep", "alice"), ("bob",))]
    result = edit(PullRequestAdapter(service), remove_assignee="remove", add_reviewer="bob", remove_reviewer="old")
    service.update.assert_not_called()
    service.remove_assignees.assert_called_once_with("owner", "repo", 42, "remove")
    service.remove_reviewers.assert_called_once_with("owner", "repo", 42, "old")
    assert result == item(("keep", "alice"), ("bob",))


def test_already_applied_changes_are_read_only_noop():
    service = MagicMock()
    service.get.return_value = item(("alice",))
    assert edit(PullRequestAdapter(service), remove_reviewer="absent") == item(("alice",))
    assert [call[0] for call in service.mock_calls] == ["get"]


def test_mixed_edit_rereads_after_patch_even_when_people_need_no_write():
    service = MagicMock()
    service.get.side_effect = [item(("alice",), title="Old"), item(("alice",), title="New")]
    result = edit(PullRequestAdapter(service), title="New")
    assert result["title"] == "New"
    service.update.assert_called_once_with("owner", "repo", 42, title="New")
    service.add_assignees.assert_not_called()
    assert service.get.call_count == 2


@pytest.mark.parametrize("operation", [create, edit])
def test_people_and_milestone_share_one_verified_final_snapshot(operation):
    service = MagicMock()
    service.create.return_value = {"number": 42}
    service.get.side_effect = [item(milestone={"number": 1}), item(("alice",), milestone={"number": 7})]
    result = operation(PullRequestAdapter(service), milestone="7")
    final = result.item if operation is create else result
    assert final["milestone"] == {"number": 7}
    assert final["assignees"] == [person("alice")]
    assert service.get.call_count == 2


@pytest.mark.parametrize("operation", [create, edit])
@pytest.mark.parametrize("overrides", [{"id": 2042}, {"assignees": []}, {"milestone": {"number": 8}}])
def test_combined_people_milestone_checks_every_postcondition_on_same_snapshot(operation, overrides):
    service = MagicMock()
    service.create.return_value = {"number": 42}
    after = item(("alice",), milestone={"number": 7})
    after.update(overrides)
    service.get.side_effect = [item(), after]
    with pytest.raises(click.ClickException, match="no write was repeated"):
        operation(PullRequestAdapter(service), milestone="7")
    service.add_assignees.assert_called_once()
    assert service.get.call_count == 2


@pytest.mark.parametrize("response", [None, {}, {"number": True}, {"number": 0}])
def test_create_missing_number_does_not_repeat_create_or_assign(response):
    service = MagicMock()
    service.create.return_value = response
    with pytest.raises(click.ClickException, match="creation may have succeeded"):
        create(PullRequestAdapter(service))
    service.create.assert_called_once()
    service.get.assert_not_called()
    service.add_assignees.assert_not_called()


@pytest.mark.parametrize(
    "before",
    [
        None,
        {},
        item(number=99),
        item(number=True),
        item(id=None),
        item(assignees=None),
        item(assignees=[None]),
        item(assignees=[{"login": "alice"}]),
        item(assignees=[{"login": "alice", "id": True}]),
        item(assignees=[person("a"), person("a")]),
    ],
)
def test_unverifiable_preflight_never_writes(before):
    service = MagicMock()
    service.get.return_value = before
    with pytest.raises(click.ClickException, match="no PR write was attempted"):
        edit(PullRequestAdapter(service), title="Do not write")
    service.update.assert_not_called()
    service.add_assignees.assert_not_called()


@pytest.mark.parametrize(
    "after",
    [
        item(),
        item(("alice",)),
        item(("keep", "alice"), number=99),
        item(("keep", "alice"), id=2042),
        item(assignees=[{"login": "keep", "id": "swapped"}, person("alice")]),
        item(("keep", "alice", "remove")),
    ],
)
def test_unconfirmed_readback_fails_without_repeating_mutations(after):
    service = MagicMock()
    service.get.side_effect = [item(("keep", "remove")), after]
    with pytest.raises(click.ClickException, match="no write was repeated"):
        edit(PullRequestAdapter(service), remove_assignee="remove")
    service.add_assignees.assert_called_once()
    service.remove_assignees.assert_called_once()
    assert service.get.call_count == 2


@pytest.mark.parametrize(
    "failure", [APIError("synthetic rejection"), NetworkError("synthetic timeout"), ValueError("private")]
)
def test_partial_create_personnel_failure_does_not_recreate_or_continue(failure):
    service = MagicMock()
    service.create.return_value = {"number": 42}
    service.get.return_value = item()
    service.add_assignees.side_effect = failure
    with pytest.raises(click.ClickException, match="no write was repeated") as error:
        create(PullRequestAdapter(service), reviewers=("bob",))
    assert "private" not in str(error.value)
    service.create.assert_called_once()
    service.add_assignees.assert_called_once()
    service.add_reviewers.assert_not_called()


def test_read_failure_after_create_is_explicitly_partial():
    service = MagicMock()
    service.create.return_value = {"number": 42}
    service.get.side_effect = NetworkError("synthetic timeout")
    with pytest.raises(click.ClickException, match="may have been created or updated"):
        create(PullRequestAdapter(service))
    service.add_assignees.assert_not_called()


def test_concurrent_additions_are_preserved_not_rejected():
    service = MagicMock()
    service.get.side_effect = [item(("keep",)), item(("keep", "alice", "concurrent"))]
    assert edit(PullRequestAdapter(service))["assignees"] == [person(x) for x in ("keep", "alice", "concurrent")]


def test_dry_run_describes_followup_operations_without_writes():
    service = MagicMock()
    result = create(PullRequestAdapter(service), dry_run=True, reviewers=("bob",))
    assert result.item["people_operations"] == {"assignees": ("alice",), "approval_reviewers": ("bob",)}
    assert not service.mock_calls
