from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.commands._created_output import created_output
from gitcode_cli.errors import NetworkError
from gitcode_cli.json_projection import project_issue, project_pr


def _output(item, read, *, fields="number,state", kind="Issue", **kwargs):
    return created_output(
        item,
        kind=kind,
        json_fields=fields,
        jq_query=None,
        project=project_pr if kind == "PR" else project_issue,
        read=read,
        **kwargs,
    )


def test_complete_selected_fields_and_unknown_custom_fields_need_no_get():
    read = MagicMock()
    result = _output({"number": "42", "state": "opened"}, read, fields="number,state,unknownCustom")
    assert result["number"] == 42 and result["state"] == "OPEN"
    read.assert_not_called()


def test_create_pr_aliases_need_no_get():
    read = MagicMock()
    result = _output(
        {"source_branch": "feature", "target_branch": "main", "work_in_progress": False},
        read,
        kind="PR",
        fields="head,base,draft",
    )
    assert result["head"] == {"ref": "feature"} and result["draft"] is False
    read.assert_not_called()


def test_missing_milestone_reads_once_and_uses_server_snapshot():
    read = MagicMock(return_value={"number": 42, "state": "closed", "milestone": {"number": 7}})
    result = _output({"number": "42", "state": "open"}, read, fields="milestone", requested_milestone=True)
    assert result["milestone"] == {"number": 7}
    assert result["state"] == "CLOSED"
    read.assert_called_once_with(42)


def test_explicit_null_is_preserved_and_missing_after_get_is_not_retried():
    read = MagicMock(return_value={"number": 42})
    assert _output({"number": 42, "milestone": None}, read, fields="milestone")["milestone"] is None
    read.assert_not_called()
    result = _output({"number": 42}, read, fields="createdAt")
    assert result["createdAt"] is None
    read.assert_called_once_with(42)


def test_already_verified_metadata_snapshot_never_adds_an_extra_get():
    read = MagicMock()
    result = _output({"number": 42}, read, fields="createdAt", readback_done=True)
    assert result["createdAt"] is None
    read.assert_not_called()


@pytest.mark.parametrize("snapshot", [None, [], {}, {"number": 43}, {"number": True}])
def test_malformed_or_mismatched_readback_is_partial_success(snapshot):
    read = MagicMock(return_value=snapshot)
    with pytest.raises(click.ClickException, match="Issue creation returned #42"):
        _output({"number": 42}, read, fields="createdAt")
    read.assert_called_once_with(42)


@pytest.mark.parametrize("error", [NetworkError("Synthetic timeout"), ValueError("Bad JSON")])
def test_read_error_explains_no_repeated_create(error):
    read = MagicMock(side_effect=error)
    with pytest.raises(click.ClickException, match="no create request was repeated"):
        _output({"number": 42}, read, fields="createdAt")
    read.assert_called_once_with(42)


@pytest.mark.parametrize("item", [None, [], {}, {"number": True}, {"number": 0}])
def test_no_server_number_never_searches_or_guesses(item):
    read = MagicMock()
    with pytest.raises(click.ClickException, match="creation may have succeeded"):
        _output(item, read, fields="createdAt")
    read.assert_not_called()


def test_jq_uses_documented_field_set_and_reads_at_most_once():
    read = MagicMock(return_value={"number": 42, "state": "opened"})
    result = created_output(
        {"number": 42},
        kind="PR",
        json_fields=None,
        jq_query=".state",
        project=project_pr,
        read=read,
    )
    assert result["state"] == "OPEN"
    read.assert_called_once_with(42)


def test_api_only_create_url_gets_one_opportunity_for_a_web_url():
    read = MagicMock(return_value={"number": 42, "html_url": "https://gitcode.com/o/r/issues/42"})
    result = _output({"number": 42, "url": "https://gitcode.com/api/v5/repos/o/r/issues/42"}, read, fields="url")
    assert result["url"] == "https://gitcode.com/o/r/issues/42"
    read.assert_called_once_with(42)
