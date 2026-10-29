"""Offline CLI → adapter → service → HTTP contracts for final-label removal."""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.context import AppContext

ORIGIN = "https://labels.gitcode.invalid"
TOKEN = "synthetic-label-contract-token"
ISSUE_PATH = "/api/v5/repos/owner/repo/issues/42"
UPDATE_PATH = "/api/v5/repos/owner/issues/42"


@pytest.fixture
def http_cli(monkeypatch):
    def reject_ambient_credentials(*args, **kwargs):
        raise AssertionError("HTTP contracts must not read ambient credentials or configuration")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject_ambient_credentials)
    monkeypatch.setattr("gitcode_cli.config.get_token", reject_ambient_credentials)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject_ambient_credentials)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(token=TOKEN, base_url=f"{ORIGIN}/api/v5/")
        monkeypatch.setattr(AppContext, "client", lambda self: client)
        try:
            yield router, CliRunner()
        finally:
            client.close()


def _route(router, method, path, *, responses=None, payload=None, error=None):
    remaining = list(responses or [(200, {})])

    def respond(request):
        assert request.method == method
        assert request.url.scheme == "https" and request.url.host == "labels.gitcode.invalid"
        assert request.url.raw_path.split(b"?", 1)[0] == path.encode("ascii")
        assert request.url.params.multi_items() == [("access_token", TOKEN)]
        assert request.headers["accept"] == "application/json"
        assert "private-token" not in request.headers
        assert "authorization" not in request.headers
        if payload is None:
            assert not request.content
        else:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == payload
            assert payload.get("labels") != ""
        if error is not None:
            raise error("Synthetic timeout", request=request)
        assert remaining, "Unexpected repeated request"
        status, body = remaining.pop(0)
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    return router.request(method, ORIGIN + path).mock(side_effect=respond)


def _edit(runner, *options):
    return runner.invoke(main, ["--token", TOKEN, "issue", "edit", "42", "-R", "owner/repo", *options])


@pytest.mark.parametrize("name", ["bug", "help wanted", "scope/bug", "标签%2F?#"])
def test_last_label_delete_encodes_name_once_and_has_no_patch(http_cli, name):
    router, runner = http_cli
    get = _route(router, "GET", ISSUE_PATH, responses=[(200, {"labels": [name]}), (200, {"labels": []})])
    delete = _route(router, "DELETE", ISSUE_PATH + "/labels/" + quote(name, safe=""), responses=[(204, None)])

    result = _edit(runner, "--remove-label", name)

    assert result.exit_code == 0, result.output
    assert "Edited issue #42" in result.output
    assert get.call_count == 2
    assert delete.call_count == 1


def test_all_labels_deleted_once_and_repeated_edit_is_noop(http_cli):
    router, runner = http_cli
    get = _route(
        router,
        "GET",
        ISSUE_PATH,
        responses=[(200, {"labels": ["bug", "docs"]}), (200, {"labels": []}), (200, {"labels": []})],
    )
    bug = _route(router, "DELETE", ISSUE_PATH + "/labels/bug")
    docs = _route(router, "DELETE", ISSUE_PATH + "/labels/docs")

    for _ in range(2):
        result = _edit(runner, "--remove-label", "bug", "--remove-label", "docs", "--remove-label", "bug")
        assert result.exit_code == 0, result.output

    assert get.call_count == 3
    assert bug.call_count == docs.call_count == 1


def test_mixed_edit_omits_labels_from_patch_and_keeps_concurrent_label(http_cli):
    router, runner = http_cli
    _route(
        router,
        "GET",
        ISSUE_PATH,
        responses=[(200, {"labels": ["bug"]}), (200, {"labels": ["concurrent"], "title": "Updated"})],
    )
    patch = _route(router, "PATCH", UPDATE_PATH, payload={"repo": "repo", "title": "Updated", "body": "Body"})
    delete = _route(router, "DELETE", ISSUE_PATH + "/labels/bug")

    result = _edit(runner, "--title", "Updated", "--body", "Body", "--remove-label", "bug")

    assert result.exit_code == 0, result.output
    assert patch.call_count == delete.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "PATCH", "DELETE", "GET"]


@pytest.mark.parametrize("add", [False, True])
def test_intermediate_removal_and_addition_keep_nonempty_patch_contract(http_cli, add):
    router, runner = http_cli
    _route(router, "GET", ISSUE_PATH, responses=[(200, {"labels": ["keep", "bug"]})])
    _route(
        router,
        "PATCH",
        UPDATE_PATH,
        payload={"repo": "repo", "title": "Unchanged", "labels": "keep,docs" if add else "keep"},
    )
    options = ["--title", "Unchanged", "--remove-label", "bug"]
    if add:
        options.extend(["--add-label", "docs"])

    result = _edit(runner, *options)

    assert result.exit_code == 0, result.output
    assert [entry.request.method for entry in router.calls] == ["GET", "PATCH"]


@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
def test_delete_error_after_patch_reports_partial_success_without_retry(http_cli, status):
    router, runner = http_cli
    _route(router, "GET", ISSUE_PATH, responses=[(200, {"labels": ["bug"]})])
    _route(router, "PATCH", UPDATE_PATH, payload={"repo": "repo", "title": "Updated"})
    delete = _route(
        router, "DELETE", ISSUE_PATH + "/labels/bug", responses=[(status, {"message": "Synthetic rejection"})]
    )

    result = _edit(runner, "--title", "Updated", "--remove-label", "bug")

    assert result.exit_code == 1
    assert "field update completed=True" in result.output
    assert "label deletion failed" in result.output
    assert "Edited issue" not in result.output
    assert delete.call_count == 1
    assert [entry.request.method for entry in router.calls] == ["GET", "PATCH", "DELETE"]


def test_delete_timeout_stops_without_retry_or_readback(http_cli):
    router, runner = http_cli
    _route(router, "GET", ISSUE_PATH, responses=[(200, {"labels": ["bug"]})])
    delete = _route(router, "DELETE", ISSUE_PATH + "/labels/bug", error=httpx.ReadTimeout)

    result = _edit(runner, "--remove-label", "bug")

    assert result.exit_code == 1
    assert "may have taken effect" in result.output
    assert "no automatic retry or rollback" in result.output
    assert "Edited issue" not in result.output
    assert delete.call_count == 1


@pytest.mark.parametrize("readback", [{}, {"labels": None}, {"labels": ["bug"]}])
def test_missing_malformed_or_unchanged_readback_is_not_success(http_cli, readback):
    router, runner = http_cli
    get = _route(router, "GET", ISSUE_PATH, responses=[(200, {"labels": ["bug"]}), (200, readback)])
    delete = _route(router, "DELETE", ISSUE_PATH + "/labels/bug")

    result = _edit(runner, "--remove-label", "bug")

    assert result.exit_code == 1
    assert "1 label deletion request(s) succeeded; readback failed" in result.output
    assert "Edited issue" not in result.output
    assert get.call_count == 2
    assert delete.call_count == 1
