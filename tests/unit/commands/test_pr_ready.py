"""Idempotent draft-state transitions without live API or Git operations."""

from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.errors import APIError, NetworkError


@pytest.fixture
def client(monkeypatch):
    client = MagicMock()
    monkeypatch.setenv("GC_TOKEN", "synthetic-ready-token")
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    return client


def _ready(undo):
    args = ["pr", "ready", "42", "-R", "owner/repo"]
    if undo:
        args.append("--undo")
    return CliRunner().invoke(main, args)


@pytest.mark.parametrize("undo", [False, True])
def test_already_requested_state_is_success_without_patch(client, undo):
    client.get.return_value = {"number": 42, "draft": undo}

    result = _ready(undo)

    assert result.exit_code == 0, result.output
    assert "already" in result.output
    assert client.mock_calls == [call.get("/repos/owner/repo/pulls/42")]


@pytest.mark.parametrize("undo", [False, True])
def test_transition_is_written_once_and_verified_before_success(client, undo):
    client.get.side_effect = [{"number": 42, "draft": not undo}, {"number": 42, "draft": undo}]
    client.patch.return_value = {"number": 42}

    result = _ready(undo)

    assert result.exit_code == 0, result.output
    assert ("Converted" if undo else "Marked") in result.output
    assert client.mock_calls == [
        call.get("/repos/owner/repo/pulls/42"),
        call.patch("/repos/owner/repo/pulls/42", json={"draft": undo}),
        call.get("/repos/owner/repo/pulls/42"),
    ]


@pytest.mark.parametrize("undo", [False, True])
@pytest.mark.parametrize("item", [None, [], {}, {"draft": None}, {"draft": 0}, {"draft": 1}, {"draft": "false"}])
def test_unknown_initial_state_never_writes(client, undo, item):
    client.get.return_value = item

    result = _ready(undo)

    assert result.exit_code == 1
    assert "no update was attempted" in result.output
    client.patch.assert_not_called()


@pytest.mark.parametrize("undo", [False, True])
@pytest.mark.parametrize("item", [None, [], {}, {"draft": None}, {"draft": 0}, {"draft": 1}, {"draft": "true"}])
def test_unknown_final_state_is_not_reported_as_success(client, undo, item):
    client.get.side_effect = [{"draft": not undo}, item]

    result = _ready(undo)

    assert result.exit_code == 1
    assert "not confirmed" in result.output
    assert "before retrying" in result.output
    assert "Marked" not in result.output and "Converted" not in result.output
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/42", json={"draft": undo})


@pytest.mark.parametrize("undo", [False, True])
def test_unchanged_final_state_is_not_reported_as_success(client, undo):
    client.get.return_value = {"draft": not undo}

    result = _ready(undo)

    assert result.exit_code == 1
    assert "not confirmed" in result.output
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/42", json={"draft": undo})


def test_initial_read_failure_never_writes(client):
    client.get.side_effect = APIError("Read refused", 403)

    result = _ready(False)

    assert result.exit_code == 1
    assert "Read refused" in result.output
    client.patch.assert_not_called()


@pytest.mark.parametrize("error", [APIError("Bad request", 400), NetworkError("Write timeout")])
def test_write_failure_is_not_swallowed_or_retried(client, error):
    client.get.return_value = {"draft": True}
    client.patch.side_effect = error

    result = _ready(False)

    assert result.exit_code == 1
    assert "Marked" not in result.output
    client.get.assert_called_once_with("/repos/owner/repo/pulls/42")
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/42", json={"draft": False})


@pytest.mark.parametrize("error", [APIError("Read refused", 403), NetworkError("Read timeout")])
def test_readback_failure_reports_possible_partial_success_without_retry(client, error):
    client.get.side_effect = [{"draft": True}, error]

    result = _ready(False)

    assert result.exit_code == 1
    assert "update may have succeeded" in result.output
    assert "before retrying" in result.output
    client.patch.assert_called_once_with("/repos/owner/repo/pulls/42", json={"draft": False})
    assert client.get.call_count == 2
