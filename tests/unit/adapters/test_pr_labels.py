from unittest.mock import Mock

import click
import pytest

from gitcode_cli.adapters._pr_labels import PRLabelPlan
from gitcode_cli.adapters.pulls import PullRequestAdapter
from gitcode_cli.errors import APIError


def pr(*names, **overrides):
    return {
        "number": 42,
        "id": 1042,
        "labels": [{"name": name, "id": sum(map(ord, name))} for name in names],
        **overrides,
    }


def edit(service, **overrides):
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
    options.update(remove_milestone=False, **overrides)
    return PullRequestAdapter(service).edit_pr("owner", "repo", 42, **options)


@pytest.mark.parametrize("value", ["", " ", ",", "a,", ",b", "a, ,b", ".", "..", "x\nq", "x\x7fq", "x\n", "\tx"])
@pytest.mark.parametrize("key", ["add", "remove"])
def test_ambiguous_inputs_fail_before_reads_or_writes(value, key):
    service = Mock()
    with pytest.raises(click.UsageError):
        PRLabelPlan(service, **{key: value, "remove" if key == "add" else "add": None})
    assert not service.mock_calls


def test_conflicting_labels_fail_before_reads_or_writes():
    service = Mock()
    with pytest.raises(click.UsageError, match="same PR label"):
        PRLabelPlan(service, add="a, b, a", remove="b")
    assert not service.mock_calls


def test_comma_input_dedup_noop_and_preservation():
    service = Mock()
    before = pr("keep", "old")
    after = pr("keep", "new", "concurrent")
    service.get.side_effect = [before, after]
    result = edit(service, add_label="new,new,keep", remove_label="old,missing,old")
    assert result is after
    service.add_labels.assert_called_once_with("owner", "repo", 42, ["new"])
    service.remove_label.assert_called_once_with("owner", "repo", 42, "old")
    service.update.assert_not_called()
    assert service.get.call_count == 2


def test_noop_avoids_all_writes_and_extra_read():
    service = Mock()
    service.get.return_value = pr("keep")
    assert edit(service, add_label="keep", remove_label="missing") == pr("keep")
    assert [call[0] for call in service.mock_calls] == ["get"]


@pytest.mark.parametrize(
    "item",
    [
        None,
        [],
        pr(number=43),
        pr(id=True),
        pr(labels=None),
        pr(labels=["a"]),
        pr(labels=[{}]),
        pr(labels=[{"name": "a", "id": 0}]),
        pr(labels=[{"name": "", "id": 1}]),
        pr(labels=[{"name": "a", "id": 1}, {"name": "a", "id": 2}]),
    ],
)
def test_malformed_preflight_never_mutates(item):
    service = Mock()
    service.get.return_value = item
    with pytest.raises(click.ClickException, match="no PR write was attempted"):
        edit(service, title="new", remove_label="old")
    assert [call[0] for call in service.mock_calls] == ["get"]


@pytest.mark.parametrize(
    "after",
    [
        None,
        pr(id=1043),
        pr(number=43),
        pr("keep", "old", "new"),
        pr("new"),
        pr("keep"),
        pr("keep", "new", labels=[{"name": "keep", "id": 999}, {"name": "new", "id": 330}]),
    ],
)
def test_unconfirmed_readback_reports_partial_and_never_repeats(after):
    service = Mock()
    service.get.side_effect = [pr("keep", "old"), after]
    with pytest.raises(click.ClickException, match="no write was repeated or rolled back"):
        edit(service, add_label="new", remove_label="old")
    assert service.add_labels.call_count == service.remove_label.call_count == 1
    assert service.get.call_count == 2


@pytest.mark.parametrize("stage", ["preflight", "add", "delete", "readback"])
def test_api_errors_are_not_retried(stage):
    service = Mock()
    service.get.side_effect = [pr("old"), pr("new")]
    if stage == "preflight":
        service.get.side_effect = APIError("synthetic")
    elif stage == "readback":
        service.get.side_effect = [pr("old"), APIError("synthetic")]
    else:
        getattr(service, "add_labels" if stage == "add" else "remove_label").side_effect = APIError("synthetic")
    with pytest.raises(click.ClickException, match="no PR write" if stage == "preflight" else "may have been updated"):
        edit(service, add_label="new", remove_label="old")
    assert service.add_labels.call_count <= 1 and service.remove_label.call_count <= 1
    service.update.assert_not_called()


def test_mixed_generic_update_with_label_noop_requires_fresh_confirmation():
    service = Mock()
    service.get.side_effect = [pr("keep"), pr()]
    with pytest.raises(click.ClickException, match="labels were not confirmed"):
        edit(service, title="new", add_label="keep")
    service.update.assert_called_once_with("owner", "repo", 42, title="new")
    assert service.get.call_count == 2
    service.add_labels.assert_not_called()


def test_people_final_snapshot_cannot_hide_label_regression():
    service = Mock()
    service.get.side_effect = [
        pr("old", assignees=[]),
        pr("old", assignees=[{"login": "alice", "id": 1}]),
    ]
    with pytest.raises(click.ClickException, match="labels were not confirmed"):
        edit(service, add_assignee="alice", remove_label="old")
    service.add_assignees.assert_called_once_with("owner", "repo", 42, "alice")
    service.remove_label.assert_called_once_with("owner", "repo", 42, "old")
    assert service.get.call_count == 2


def test_people_preflight_also_validates_labels_before_any_write():
    service = Mock()
    service.get.return_value = pr(assignees=[], labels=None)
    with pytest.raises(click.ClickException, match="no PR write was attempted"):
        edit(service, title="new", add_assignee="alice", remove_label="old")
    assert [call[0] for call in service.mock_calls] == ["get"]


def test_milestone_uses_final_label_snapshot_without_an_extra_read():
    service = Mock()
    service.get.side_effect = [pr("old"), pr(milestone={"number": 8})]
    result = edit(service, milestone="8", remove_label="old")
    assert result["milestone"] == {"number": 8}
    assert service.get.call_count == 2
    service.update.assert_called_once_with("owner", "repo", 42, milestone_number=8)
