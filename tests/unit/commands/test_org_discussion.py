"""Exercise the org/discussion Click groups with only a synthetic, in-process client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call

import click
import pytest
from click.testing import CliRunner

from gitcode_cli.commands import _community_pages
from gitcode_cli.commands.discussion import discussion_group
from gitcode_cli.commands.org import org_group
from gitcode_cli.errors import APIError, GCError


@pytest.fixture
def client():
    return MagicMock()


@pytest.fixture
def run(client):
    @click.group()
    @click.option("-R", "repo")
    @click.pass_context
    def root(ctx, repo):
        app = MagicMock()
        app.client.return_value = client
        app.repo = repo
        ctx.obj = {"app": app}

    root.add_command(org_group)
    root.add_command(discussion_group)
    runner = CliRunner()

    def invoke(*args, stdin=None):
        return runner.invoke(root, list(args), input=stdin)

    return invoke


def row(number, *, closed=0, updated="2026-01-01T00:00:00Z", **kwargs):
    return {
        "id": str(number),
        "number": number,
        "title": f"Topic {number}",
        "is_closed": closed,
        "updated_at": updated,
        **kwargs,
    }


def test_org_list_paginated_and_limited(run, client):
    client.get.side_effect = [[{"login": f"org{i}"} for i in range(100)], [{"login": "last"}, {"login": "omit"}]]
    result = run("org", "ls", "-L", "101")
    assert result.exit_code == 0
    assert len(result.output.splitlines()) == 101
    assert result.output.splitlines()[-1] == "last"
    assert client.get.call_args_list == [call("/users/orgs", params={"page": p, "per_page": 100}) for p in (1, 2)]


def test_org_empty(run, client):
    client.get.return_value = []
    result = run("org", "list")
    assert result.exit_code == 0 and result.output == ""
    client.get.assert_called_once_with("/users/orgs", params={"page": 1, "per_page": 30})


@pytest.mark.parametrize("rows", [{}, [None], [{"id": "1"}], [{"login": "a"}, {"login": "a"}]])
def test_org_rejects_malformed_pages_without_partial_output(run, client, rows):
    client.get.return_value = rows
    result = run("org", "list")
    assert isinstance(result.exception, APIError)
    assert not result.output


def test_default_state_updated_order_uses_all_pages(run, client):
    page1 = [row(i) for i in range(1, 101)]
    page2 = [
        row(101, closed=1, updated="2026-02-01T00:00:00Z"),
        row(102, updated="2026-01-01T03:30:00+02:00"),
        row(103, updated="2026-01-01T02:00:00Z"),
    ]
    client.get.side_effect = [page1, page2]
    result = run("-R", "O/R", "discussion", "ls", "-L", "2", "--json", "number,title")
    assert result.exit_code == 0, result.exception
    assert json.loads(result.output) == [{"number": 103, "title": "Topic 103"}, {"number": 102, "title": "Topic 102"}]
    assert client.get.call_args_list == [
        call("/repos/O/R/discuss", params={"page": p, "per_page": 100, "sort": "created", "direction": "desc"})
        for p in (1, 2)
    ]


def test_created_order_filters_across_pages(run, client):
    client.get.side_effect = [
        [row(i) for i in range(100, 0, -1)],
        [
            row(103, closed=1),
            row(102, closed=1, author={"login": "a"}, category={"name": "Other"}),
            row(101, closed=1, author={"login": "a"}, category={"name": "News"}),
        ],
    ]
    result = run(
        "discussion",
        "list",
        "-R",
        "O/R",
        "--sort",
        "created",
        "--state",
        "closed",
        "-c",
        "News",
        "-A",
        "a",
        "-S",
        "hello",
        "-L",
        "1",
    )
    assert result.exit_code == 0, result.exception
    assert "#101\tCLOSED\tTopic 101" in result.output
    assert len(client.get.call_args_list) == 2
    assert client.get.call_args.kwargs["params"] == {
        "page": 2,
        "per_page": 100,
        "sort": "created",
        "direction": "desc",
        "search": "hello",
    }


@pytest.mark.parametrize(
    "response",
    [
        [row(1, updated="not a time")],
        [row(1, updated="2026-01-01")],
        [row(1, closed="alien")],
    ],
)
def test_unknown_state_or_update_not_silently_guessed(run, client, response):
    client.get.return_value = response
    result = run("discussion", "list", "-R", "O/R")
    assert isinstance(result.exception, APIError)
    assert not result.output


def test_page_safety_cap_fails_explicitly(run, client, monkeypatch):
    monkeypatch.setattr(_community_pages, "_MAX_PAGES", 1)
    client.get.return_value = [row(i) for i in range(1, 101)]
    result = run("discussion", "list", "-R", "O/R", "-L", "1")
    assert isinstance(result.exception, APIError)
    assert "incomplete" in str(result.exception)
    assert not result.output


@pytest.mark.parametrize(
    "args",
    [
        ["view", "4", "-R", "github.com/O/R"],
        ["create", "-R", "github.com/O/R", "-t", "x", "-c", "y", "-b", "z"],
        ["comment", "0", "-b", "comment"],
        ["edit", "7", "-t", "x", "-b", "z"],
        ["list", "-L", "0"],
        ["list", "-R", "O/R", "--json", "body"],
        ["view", "2", "--json", "comments"],
        ["comment", "5", "-b", "body", "-F", "-"],
        ["create", "-R", "O/R", "-t", " ", "-c", "cat", "-b", "x"],
    ],
)
def test_bad_input_no_api_call(run, client, args):
    assert run("discussion", *args).exit_code != 0
    assert not client.mock_calls


def test_view_with_comments_reads_exact_endpoints(run, client):
    client.get.side_effect = [
        row(2, md_content="body", is_lock=1, is_answered="0"),
        [{"id": "a", "md_content": "first"}],
    ]
    result = run(
        "discussion",
        "view",
        "2",
        "-R",
        "O/R",
        "-c",
        "--order",
        "oldest",
        "--json",
        "number,body,comments,locked,answered",
    )
    assert result.exit_code == 0, result.exception
    assert json.loads(result.output) == {
        "number": 2,
        "body": "body",
        "comments": [{"id": "a", "md_content": "first"}],
        "locked": True,
        "answered": False,
    }
    assert client.get.call_args_list == [
        call("/repos/O/R/discuss/2"),
        call("/repos/O/R/discuss/2/comment", params={"order": "time_asc", "page": 1, "per_page": 30}),
    ]


def test_view_human(run, client):
    client.get.side_effect = [
        row(2, md_content="hello"),
        [{"id": "x", "md_content": "question", "author": {"login": "a"}}],
    ]
    result = run("-R", "O/R", "discussion", "view", "2", "-c")
    assert result.exit_code == 0 and "hello" in result.output and "a: question" in result.output


def test_view_rejects_wrong_number(run, client):
    client.get.return_value = row(3)
    assert isinstance(run("-R", "O/R", "discussion", "view", "2").exception, APIError)
    client.get.assert_called_once()


def test_single_post_create_with_stdin(run, client):
    client.post.return_value = row(2, title="Title", md_content="one\ntwo\n", category={"name": "Q&A"})
    result = run("discussion", "create", "-R", "O/R", "-t", "Title", "-c", "Q&A", "-F", "-", stdin="one\ntwo\n")
    assert result.exit_code == 0 and "#2" in result.output
    assert client.mock_calls == [
        call.post("/repos/O/R/discuss", json={"title": "Title", "category_name": "Q&A", "md_content": "one\ntwo\n"})
    ]


def test_single_put_edit(run, client):
    client.put.return_value = row(7, title="Title", md_content="text", category={"name": "Q&A"})
    result = run("discussion", "edit", "7", "-R", "O/R", "-t", "Title", "-c", "Q&A", "-b", "text")
    assert result.exit_code == 0 and "#7" in result.output
    assert client.mock_calls == [
        call.put("/repos/O/R/discuss/7", json={"title": "Title", "category_name": "Q&A", "md_content": "text"})
    ]


def test_single_post_comment(run, client):
    client.get.return_value = row(7, id="discussion-immutable-id")
    client.post.return_value = {"id": "c1", "discuss_id": "discussion-immutable-id", "md_content": "text", "type": 1}
    result = run("discussion", "comment", "7", "-R", "O/R", "-b", "text")
    assert result.exit_code == 0 and "c1" in result.output
    assert client.mock_calls == [
        call.get("/repos/O/R/discuss/7"),
        call.post("/repos/O/R/discuss/7/comment", json={"md_content": "text"}),
    ]


@pytest.mark.parametrize(
    ("args", "result"),
    [
        (["create", "-t", "t", "-c", "c", "-b", "b"], {}),
        (["edit", "7", "-t", "t", "-c", "c", "-b", "b"], {"number": 6}),
        (["comment", "2", "-b", "hello"], None),
    ],
)
def test_uncertain_write_never_retried(run, client, args, result):
    client.post.return_value = client.put.return_value = result
    client.get.return_value = row(2)
    response = run("-R", "O/R", "discussion", *args)
    assert isinstance(response.exception, GCError) and "before retrying" in str(response.exception)
    mutation = client.put if args[0] == "edit" else client.post
    mutation.assert_called_once()
    assert client.get.call_count == int(args[0] == "comment")
    assert not response.output


@pytest.mark.parametrize("command", ["create", "edit"])
@pytest.mark.parametrize(
    "different",
    [
        {"id": ""},
        {"id": "x\x1b"},
        {"number": True},
        {"title": "old"},
        {"md_content": "old"},
        {"category": {"name": "Old"}},
        {"category": "Q&A"},
    ],
)
def test_discussion_write_response_must_match_request(run, client, command, different):
    client.post.return_value = client.put.return_value = {
        **row(7, title="Title", md_content="body", category={"name": "Q&A"}),
        **different,
    }
    number = ("7",) if command == "edit" else ()
    response = run("-R", "O/R", "discussion", command, *number, "-t", "Title", "-b", "body", "-c", "Q&A")
    assert isinstance(response.exception, APIError) and "before retrying" in str(response.exception)
    assert not response.output
    (client.put if command == "edit" else client.post).assert_called_once()
    client.get.assert_not_called()


@pytest.mark.parametrize("readback", [None, row(8), row(7, id="  "), row(7, id=123), {"number": "7", "id": "opaque"}])
def test_comment_requires_proven_parent_before_post(run, client, readback):
    client.get.return_value = readback
    response = run("-R", "O/R", "discussion", "comment", "7", "-b", "body")
    assert isinstance(response.exception, APIError) and "no comment was submitted" in str(response.exception)
    assert not response.output
    client.get.assert_called_once_with("/repos/O/R/discuss/7")
    client.post.assert_not_called()


@pytest.mark.parametrize(
    "different",
    [
        {"discuss_id": "7"},
        {"discuss_id": "other"},
        {"id": ""},
        {"id": " c1 "},
        {"md_content": "old"},
        {"type": 2},
        {"type": True},
        {"type": "1"},
    ],
)
def test_comment_response_must_confirm_parent_type_and_body(run, client, different):
    client.get.return_value = row(7, id="parent-opaque")
    client.post.return_value = {"id": "c1", "discuss_id": "parent-opaque", "md_content": "body", "type": 1, **different}
    response = run("-R", "O/R", "discussion", "comment", "7", "-b", "body")
    assert isinstance(response.exception, APIError) and "before retrying" in str(response.exception)
    assert not response.output
    assert client.mock_calls == [
        call.get("/repos/O/R/discuss/7"),
        call.post("/repos/O/R/discuss/7/comment", json={"md_content": "body"}),
    ]


@pytest.mark.parametrize("json_output", [(), ("--json", "number,comments")])
@pytest.mark.parametrize(
    "malformed",
    [{"id": "wrong", "author": "not-object"}, {"id": "bad-body", "md_content": []}, {"id": 123}, {"id": "bad\x1b"}],
)
def test_view_never_prints_partial_output_when_comments_malformed(run, client, json_output, malformed):
    client.get.side_effect = [row(7, md_content="topic"), [{"id": "valid", "md_content": "first"}, malformed]]
    response = run("-R", "O/R", "discussion", "view", "7", "--comments", *json_output)
    assert isinstance(response.exception, APIError) and "Invalid discussion comment" in str(response.exception)
    assert not response.output
