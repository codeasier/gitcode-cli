"""Strict @me identity resolution, without executing provider requests."""

from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.adapters._current_user import resolve_me
from gitcode_cli.adapters.issues import IssueAdapter
from gitcode_cli.adapters.pulls import PullRequestAdapter
from gitcode_cli.errors import APIError, NetworkError


def test_plain_values_are_unchanged_without_lookup():
    users = MagicMock()
    values = (None, "alice", "", "alice,bob", "@other", " @me ")
    assert resolve_me(users, *values) == values
    assert not users.mock_calls
    assert resolve_me(None, "alice") == ("alice",)


def test_aliases_share_one_current_user_login_not_display_name():
    users = MagicMock()
    users.current.return_value = {"login": "account-login", "name": "Display Name", "username": "wrong"}
    assert resolve_me(users, "@me", "other", "@me", None) == ("account-login", "other", "account-login", None)
    users.current.assert_called_once_with()


@pytest.mark.parametrize(
    "current",
    [
        None,
        [],
        {},
        {"name": "display-name"},
        {"username": "username-only"},
        {"user": {"login": "nested"}},
        {"login": None},
        {"login": True},
        {"login": 42},
        {"login": ""},
        {"login": " alice"},
        {"login": "alice "},
        {"login": "Alice Smith"},
        {"login": "a\x00b"},
        {"login": "a\x7fb"},
        {"login": "@me"},
        {"login": "org/team"},
        {"login": "alice,bob"},
        {"login": "https:alice"},
    ],
)
def test_malformed_current_user_fails_closed(current):
    users = MagicMock()
    users.current.return_value = current
    with pytest.raises(click.ClickException, match="no valid login; no write was attempted"):
        resolve_me(users, "@me")


def test_alias_requires_user_service():
    with pytest.raises(click.ClickException, match="lookup is unavailable"):
        resolve_me(None, "@me")


@pytest.mark.parametrize("failure", [APIError("private"), NetworkError("private"), ValueError("private")])
def test_failed_lookup_is_explicit_and_does_not_leak_response(failure):
    users = MagicMock()
    users.current.side_effect = failure
    with pytest.raises(click.ClickException, match="lookup failed; no write was attempted") as error:
        resolve_me(users, "@me")
    assert "private" not in str(error.value)
    users.current.assert_called_once_with()


def list_prs(adapter, *, author=None, assignee=None, limit=30):
    return adapter.list_prs(
        "owner",
        "repo",
        state=None,
        author=author,
        assignee=assignee,
        base=None,
        draft=None,
        head=None,
        labels=None,
        search=None,
        limit=limit,
    )


def issue_operation(adapter, operation, identity):
    if operation == "list":
        return adapter.list_issues(
            "owner",
            "repo",
            state=None,
            labels=None,
            author=identity,
            assignee=identity,
            milestone=None,
            mention=None,
            search=None,
            limit=30,
        )
    if operation == "create":
        return adapter.create_issue(
            "owner",
            "repo",
            title="Title",
            body="Body",
            assignee=identity,
            labels=None,
            milestone=None,
        )
    return adapter.edit_issue(
        "owner",
        "repo",
        "42",
        title=None,
        body=None,
        add_assignee=identity if operation == "add" else None,
        remove_assignee=identity if operation == "remove" else None,
        add_labels=None,
        remove_labels=None,
        milestone=None,
        remove_milestone=False,
    )


def test_pr_list_resolves_both_filters_once_and_preserves_query_shape():
    service, users = MagicMock(), MagicMock()
    users.current.return_value = {"login": "alice", "name": "Wrong"}
    service.list.return_value = []
    assert list_prs(PullRequestAdapter(service, users), author="@me", assignee="@me") == []
    users.current.assert_called_once_with()
    assert service.list.call_args.kwargs["author"] == "alice"
    assert service.list.call_args.kwargs["assignee"] == "alice"
    assert service.list.call_args.kwargs["page"] == 1
    assert service.list.call_args.kwargs["per_page"] == 30


def test_zero_limit_remains_no_network_even_with_alias():
    service, users = MagicMock(), MagicMock()
    assert list_prs(PullRequestAdapter(service, users), author="@me", limit=0) == []
    assert not service.mock_calls and not users.mock_calls


@pytest.mark.parametrize("operation", ["list", "create", "add", "remove"])
def test_issue_operations_resolve_alias_before_service_use(operation):
    service, users = MagicMock(), MagicMock()
    users.current.return_value = {"login": "alice", "name": "Display Name"}
    service.list.return_value = []
    service.get.return_value = {"title": "Existing", "assignees": [{"login": "alice"}, {"login": "keep"}]}
    issue_operation(IssueAdapter(service, users), operation, "@me")
    users.current.assert_called_once_with()
    method = service.list if operation == "list" else service.create if operation == "create" else service.update
    expected = "keep" if operation == "remove" else "alice"
    assert method.call_args.kwargs["assignee"] == expected
    if operation == "list":
        assert method.call_args.kwargs["creator"] == "alice"


@pytest.mark.parametrize("operation", ["pr-list", "list", "create", "add", "remove"])
@pytest.mark.parametrize("user_available", [False, True])
def test_missing_identity_prevents_all_domain_requests(operation, user_available):
    service = MagicMock()
    users = MagicMock() if user_available else None
    if users is not None:
        users.current.return_value = {"name": "not-a-login"}
    with pytest.raises(click.ClickException):
        if operation == "pr-list":
            list_prs(PullRequestAdapter(service, users), author="@me")
        else:
            issue_operation(IssueAdapter(service, users), operation, "@me")
    assert not service.mock_calls


@pytest.mark.parametrize("operation", ["pr-list", "list", "create", "add", "remove"])
def test_plain_logins_do_not_request_current_user(operation):
    service, users = MagicMock(), MagicMock()
    service.list.return_value = []
    service.get.return_value = {"title": "Existing", "assignees": [{"login": "alice"}, {"login": "keep"}]}
    if operation == "pr-list":
        list_prs(PullRequestAdapter(service, users), author="alice", assignee="bob")
        assert service.list.call_args.kwargs["author"] == "alice"
        assert service.list.call_args.kwargs["assignee"] == "bob"
    else:
        issue_operation(IssueAdapter(service, users), operation, "alice")
    assert not users.mock_calls
