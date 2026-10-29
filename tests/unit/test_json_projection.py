"""Projection is deterministic, input-preserving and independent of write options."""

from copy import deepcopy

import pytest

from gitcode_cli.json_projection import json_number, project_issue, project_pr, repo_name_with_owner


@pytest.mark.parametrize(
    "value,expected", [(42, 42), ("0042", 42), (0, 0), (True, None), (False, None), (-1, None), ("４２", None)]
)
def test_number_type_is_integer_or_unknown(value, expected):
    assert json_number(value) == expected


@pytest.mark.parametrize("projection", [project_issue, project_pr])
@pytest.mark.parametrize("state,expected", [("opened", "OPEN"), ("open", "OPEN"), ("closed", "CLOSED"), (None, None)])
def test_common_projection_has_identical_fields_without_mutating_input(projection, state, expected):
    item = {
        "number": "42",
        "state": state,
        "html_url": "https://gitcode.com/owner/repo/issues/42",
        "url": "https://gitcode.com/api/v5/repos/owner/repo/issues/42",
        "created_at": "2026-10-29T00:00:00Z",
        "updated_at": "2026-10-29T01:00:00Z",
        "user": {"id": 1, "username": "alice"},
        "labels": [{"name": "bug"}],
    }
    before = deepcopy(item)
    result = projection(item)

    assert result["number"] == 42 and type(result["number"]) is int
    assert result["state"] == expected
    assert result["url"] == item["html_url"]
    assert result["createdAt"] == item["created_at"]
    assert result["updatedAt"] == item["updated_at"]
    assert result["author"]["login"] == "alice"
    assert result["labels"] == item["labels"]
    assert projection(result) == result
    assert item == before


@pytest.mark.parametrize(
    "fields,expected",
    [
        (
            {"html_url": "https://gitcode.com/o/r/pulls/1", "web_url": "https://gitcode.com/o/r/pulls/2"},
            "https://gitcode.com/o/r/pulls/1",
        ),
        ({"web_url": "https://gitcode.com/o/r/pulls/1"}, "https://gitcode.com/o/r/pulls/1"),
        ({"url": "https://gitcode.com/o/r/pulls/1"}, "https://gitcode.com/o/r/pulls/1"),
        ({"url": "https://api.gitcode.com/api/v5/repos/o/r/pulls/1"}, None),
        ({"url": "https://gitcode.com/api/v5/repos/o/r/pulls/1"}, None),
        ({"html_url": "https://user:secret@gitcode.com/o/r/pulls/1"}, None),
        ({"html_url": "javascript:alert(1)"}, None),
        ({"html_url": "https://[invalid"}, None),
    ],
)
def test_web_url_is_not_api_url_or_credential_bearing(fields, expected):
    assert project_issue(fields)["url"] == expected
    assert project_pr(fields)["url"] == expected


def test_api_create_shape_supplies_ref_and_draft_aliases_without_invented_repo_or_sha():
    item = {
        "number": "42",
        "state": "opened",
        "description": "Body",
        "source_branch": "feature",
        "target_branch": "main",
        "work_in_progress": 0,
    }
    result = project_pr(item)
    assert result["head"] == {"ref": "feature"}
    assert result["base"] == {"ref": "main"}
    assert result["headRefName"] == "feature" and result["baseRefName"] == "main"
    assert result["headRefOid"] is None and result["baseRefOid"] is None
    assert result["draft"] is False
    assert result["body"] == "Body"
    assert result["source_branch"] == "feature"
    assert project_pr(result) == result


def test_structured_refs_win_and_preserve_other_response_fields():
    item = {
        "head": {"ref": "actual", "sha": "abc", "repo": {"full_name": "owner/repo"}},
        "headRefName": "stale",
        "source_branch": "older",
        "baseRefName": "main",
        "body": "",
        "description": "Do not overwrite an explicitly empty body",
        "draft": False,
        "work_in_progress": True,
    }
    before = deepcopy(item)
    result = project_pr(item)
    assert result["headRefName"] == result["head"]["ref"] == "actual"
    assert result["head"] == item["head"]
    assert result["headRefOid"] == "abc"
    assert result["base"] == {"ref": "main"}
    assert result["draft"] is False and result["body"] == ""
    assert item == before


@pytest.mark.parametrize(
    "value,expected", [(False, False), (True, True), (0, False), (1, True), (2, None), ("false", None), (None, None)]
)
def test_draft_never_uses_truthiness_for_strings_or_unknown_values(value, expected):
    assert project_pr({"work_in_progress": value})["draft"] is expected


def test_missing_values_stay_unknown_instead_of_using_ids_or_request_state():
    result = project_pr({"id": 9001})
    for key in ("number", "state", "url", "createdAt", "updatedAt", "head", "base", "draft"):
        assert result[key] is None


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"path_with_namespace": "org/repo", "full_name": "Org / Repo"}, "org/repo"),
        ({"namespace": {"full_path": "parent/team", "path": "team"}, "path": "repo"}, "parent/team/repo"),
        ({"owner": {"login": "owner"}, "path": "repo", "name": "Display Name"}, "owner/repo"),
        ({"full_name": "owner/repo"}, "owner/repo"),
        ({"full_name": "Owner / Repo", "name": "Display Name"}, None),
        ({"path_with_namespace": "../repo"}, None),
        ({"path_with_namespace": "org//repo"}, None),
    ],
)
def test_repository_full_name_uses_paths_not_display_name_whitespace(item, expected):
    before = deepcopy(item)
    assert repo_name_with_owner(item) == expected
    assert item == before
