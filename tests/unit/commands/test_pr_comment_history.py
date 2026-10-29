"""Comment-history writes select only a verified, complete ordinary-comment history."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.errors import APIError, NetworkError


def _comment(comment_id=20, **overrides):
    return {
        "id": comment_id,
        "body": "Original text",
        "user": {"id": "user-7", "login": "alice"},
        "comment_type": "pr_comment",
        "created_at": "2026-10-30T10:00:00Z",
        **overrides,
    }


@pytest.fixture
def client(mock_app_context, monkeypatch):
    client = MagicMock()
    client.get.side_effect = [{"id": "user-7", "login": "alice"}, [_comment()]]
    client.patch.return_value = {}  # Documented update response has no ID.
    client.post.return_value = {"id": 99}
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
    return client


def _invoke(*args, **kwargs):
    return CliRunner().invoke(main, ["pr", "comment", "42", "-R", "owner/repo", *args], **kwargs)


def _assert_no_writes(client):
    client.post.assert_not_called()
    client.patch.assert_not_called()
    client.delete.assert_not_called()


def test_edit_selects_creation_time_across_pages_and_ignores_inline_replies_and_other_users(client):
    other = {"id": "user-8", "login": "alice", "name": "Alice"}
    newest = _comment(20, created_at="2026-10-30T10:00:00Z")
    client.get.side_effect = [
        {"id": "user-7", "login": "alice"},
        [newest] + [_comment(i, user=other) for i in range(100, 199)],
        [
            _comment(21, created_at="2026-10-30T11:00:00+02:00", updated_at="2026-11-01T12:00:00Z"),
            _comment(22, comment_type="diff_comment", created_at="2026-11-01T12:00:00Z"),
            _comment(23, user=other, reply=[_comment(24)]),
        ],
    ]

    result = _invoke("--edit-last", "--body", "Updated text")

    assert result.exit_code == 0, result.output
    assert "Edited last comment" in result.output
    assert client.get.call_args_list == [
        call("/user"),
        call("/repos/owner/repo/pulls/42/comments", params={"page": 1, "per_page": 100}),
        call("/repos/owner/repo/pulls/42/comments", params={"page": 2, "per_page": 100}),
    ]
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/comments/20", json={"body": "Updated text"})
    client.post.assert_not_called()


@pytest.mark.parametrize("body_args,stdin", [(["--body", "New"], None), (["--body-file", "-"], "New")])
def test_create_if_none_posts_only_when_complete_history_has_no_ordinary_owned_comment(client, body_args, stdin):
    client.get.side_effect = [{"login": "alice"}, [_comment(comment_type="diff_comment")]]

    result = _invoke("--edit-last", "--create-if-none", *body_args, input=stdin)

    assert result.exit_code == 0, result.output
    client.post.assert_called_once_with("/repos/owner/repo/pulls/42/comments", json={"body": "New"})
    client.patch.assert_not_called()


def test_create_if_none_edits_existing_comment_and_supports_body_file(client, tmp_path):
    body_file = tmp_path / "comment.md"
    body_file.write_text("Updated from file", encoding="utf-8")

    result = _invoke("--edit-last", "--create-if-none", "--body-file", str(body_file))

    assert result.exit_code == 0, result.output
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/comments/20", json={"body": "Updated from file"})
    client.post.assert_not_called()


@pytest.mark.parametrize("answer,expected", [("y\n", 0), ("n\n", 1), ("\n", 1)])
def test_delete_confirmation_defaults_to_no_and_never_prompts_for_body(client, answer, expected):
    result = _invoke("--delete-last", input=answer)

    assert result.exit_code == expected, result.output
    assert "Body:" not in result.output
    if expected == 0:
        client.delete.assert_called_once_with("/repos/owner/repo/pulls/comments/20")
    else:
        _assert_no_writes(client)


def test_yes_skips_only_the_delete_confirmation(client):
    result = _invoke("--delete-last", "--yes")

    assert result.exit_code == 0, result.output
    assert "[y/N]" not in result.output
    client.delete.assert_called_once_with("/repos/owner/repo/pulls/comments/20")


@pytest.mark.parametrize(
    "current_user,author",
    [
        ({"login": "alice"}, {"login": "alice"}),
        ({"id": 7}, {"id": "7"}),
        ({"id": 7, "login": "alice"}, {"id": "7", "login": "old-login"}),
    ],
)
def test_identity_uses_stable_id_or_exact_login_not_display_name(client, current_user, author):
    client.get.side_effect = [current_user, [_comment(user=author)]]

    result = _invoke("--delete-last", "--yes")

    assert result.exit_code == 0, result.output
    client.delete.assert_called_once_with("/repos/owner/repo/pulls/comments/20")


def test_tied_creation_times_use_comment_id_as_a_deterministic_tiebreaker(client):
    client.get.side_effect = [{"login": "alice"}, [_comment("21"), _comment(20)]]

    result = _invoke("--delete-last", "--yes")

    assert result.exit_code == 0, result.output
    client.delete.assert_called_once_with("/repos/owner/repo/pulls/comments/21")


@pytest.mark.parametrize("mode", [["--edit-last", "--body", "New"], ["--delete-last", "--yes"]])
def test_no_owned_comment_errors_without_creating(client, mode):
    client.get.side_effect = [{"login": "alice"}, []]

    result = _invoke(*mode)

    assert result.exit_code == 1
    assert "No ordinary pull request comment" in result.output
    _assert_no_writes(client)


@pytest.mark.parametrize("current_user", [{}, {"name": "alice"}, {"id": True}, {"login": ["alice"]}, None])
def test_unverifiable_current_user_never_creates_or_mutates(client, current_user):
    client.get.side_effect = [current_user]

    result = _invoke("--edit-last", "--create-if-none", "--body", "New")

    assert result.exit_code == 1
    assert "Unable to verify" in result.output
    _assert_no_writes(client)


@pytest.mark.parametrize(
    "history",
    [
        None,
        {},
        [None],
        [_comment(user={"name": "alice"})],
        [_comment(comment_type=None)],
        [_comment(created_at=None)],
        [_comment(created_at="2026-10-30T10:00:00")],
        [_comment(created_at="not a date")],
        [_comment(comment_id=True)],
        [_comment(comment_id=0)],
        [_comment(comment_id="../21")],
        [_comment(comment_id="²")],
    ],
)
def test_invalid_history_never_falls_back_to_create(client, history):
    client.get.side_effect = [{"id": "user-7", "login": "alice"}, history]

    result = _invoke("--edit-last", "--create-if-none", "--body", "New")

    assert result.exit_code == 1, result.output
    _assert_no_writes(client)


@pytest.mark.parametrize("failure", [APIError("Denied", 403), NetworkError("Unavailable")])
def test_incomplete_later_page_never_mutates_or_creates(client, failure):
    client.get.side_effect = [{"login": "alice"}, [_comment(i) for i in range(1, 101)], failure]

    result = _invoke("--edit-last", "--create-if-none", "--body", "New")

    assert result.exit_code == 1
    _assert_no_writes(client)


@pytest.mark.parametrize(
    "mode,method", [(["--edit-last", "--body", "New"], "patch"), (["--delete-last", "--yes"], "delete")]
)
def test_write_failure_is_not_retried_or_replaced_with_a_new_comment(client, mode, method):
    getattr(client, method).side_effect = NetworkError("Unavailable")

    result = _invoke(*mode)

    assert result.exit_code == 1
    assert getattr(client, method).call_count == 1
    client.post.assert_not_called()


@pytest.mark.parametrize("edited", ["Updated in editor", None, " \n"])
def test_editor_is_prefilled_and_cancellation_or_empty_text_does_not_write(client, monkeypatch, edited):
    editor = MagicMock(return_value=edited)
    monkeypatch.setattr("gitcode_cli.commands.pr.click.edit", editor)

    result = _invoke("--edit-last", "--editor")

    editor.assert_called_once_with("Original text")
    if edited == "Updated in editor":
        assert result.exit_code == 0, result.output
        client.patch.assert_called_once_with("/repos/owner/repo/pulls/comments/20", json={"body": edited})
    else:
        assert result.exit_code != 0
        _assert_no_writes(client)


def test_noninteractive_edit_requires_body_source(client):
    result = _invoke("--edit-last")

    assert result.exit_code == 2
    assert "required when not running interactively" in result.output
    _assert_no_writes(client)


@pytest.mark.parametrize(
    "flags",
    [
        ["--create-if-none"],
        ["--yes"],
        ["--edit-last", "--delete-last"],
        ["--delete-last", "--body", "Ignored"],
        ["--delete-last", "--editor"],
        ["--edit-last", "--body", "One", "--body-file", "missing.md"],
        ["--edit-last", "--body", "One", "--editor"],
        *[
            ["--edit-last", *option]
            for option in [
                ["--path", "a.py"],
                ["--position", "0"],
                ["--line", "1"],
                ["--side", "RIGHT"],
                ["--discussion-id", "thread"],
                ["--commit", "abc"],
                ["--web"],
            ]
        ],
    ],
)
def test_invalid_flag_combinations_fail_before_api_reads(client, flags):
    result = _invoke(*flags)

    assert result.exit_code == 2, result.output
    client.get.assert_not_called()
    _assert_no_writes(client)
