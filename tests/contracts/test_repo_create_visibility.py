"""Organization creation confirms identity and requested visibility before any local follow-up."""

from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest
import respx

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient

ORIGIN = "https://repo-create.invalid/api/v5/"
TOKEN = "synthetic-create-contract"


@pytest.fixture
def wire(cli_runner, monkeypatch, tmp_config_dir):
    monkeypatch.setenv("GC_TOKEN", TOKEN)
    monkeypatch.chdir(tmp_config_dir)
    clone = Mock()
    monkeypatch.setattr("gitcode_cli.commands.repo._git_clone", clone)
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        client = GitCodeClient(token=TOKEN, base_url=ORIGIN)
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
        try:
            yield router, cli_runner, clone
        finally:
            client.close()


@pytest.mark.parametrize("org", [True, False])
@pytest.mark.parametrize(("flags", "private"), [([], True), (["--private"], True), (["--public"], False)])
def test_cli_serializes_route_specific_visibility_once(wire, org, flags, private):
    router, runner, clone = wire
    path = "orgs/team/repos" if org else "user/repos"
    target = "team/sample" if org else "sample"
    full_name = target if org else "user/sample"
    item = {"full_name": full_name, "public": not private, "private": int(private)}
    route = router.post(ORIGIN + path).respond(200, json=item)

    result = runner.invoke(main, ["repo", "create", target, *flags])

    assert result.exit_code == 0, result.output
    assert f"https://gitcode.com/{full_name}" in result.output
    assert len(router.calls) == route.call_count == 1
    request = route.calls[0].request
    assert request.url.params.multi_items() == [("access_token", TOKEN)]
    assert request.headers["private-token"] == TOKEN
    payload = json.loads(request.content)
    key = "public" if org else "private"
    assert payload == {"name": "sample", key: int(not private) if org else private}
    assert type(payload[key]) is (int if org else bool)  # Python bools compare equal to 0 and 1.
    clone.assert_not_called()


def test_org_clone_uses_only_the_confirmed_repository(wire):
    router, runner, clone = wire
    item = {
        "full_name": "team/sample",
        "path": "sample",
        "namespace": {"path": "team", "full_path": "team"},
        "public": 0,
        "private": True,
        "visibility": "private",
        "web_url": "https://other.invalid/project",
        "http_url_to_repo": "https://other.invalid/project.git",
    }
    router.post(ORIGIN + "orgs/team/repos").respond(200, json=item)

    result = runner.invoke(main, ["repo", "create", "team/sample", "--clone"])

    assert result.exit_code == 0, result.output
    assert "other.invalid" not in result.output
    clone.assert_called_once_with("https://gitcode.com/team/sample.git")
    assert len(router.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        {},
        [],
        {"private": True},
        {"full_name": "team/sample"},
        {"full_name": "other/sample", "private": True},
        {"full_name": "team/sample", "path": "other", "private": True},
        {"full_name": "team/sample", "namespace": {"full_path": "other"}, "private": True},
        {"full_name": "team/sample", "namespace": None, "private": True},
        {"full_name": "team/sample", "private": False},
        {"full_name": "team/sample", "private": True, "visibility": "public"},
        {"full_name": "team/sample", "private": 1, "public": 1},
        {"full_name": "team/sample", "private": "true"},
        {"full_name": "team/sample", "public": 0.0},
        {"full_name": "team/sample", "private": True, "visibility": None},
    ],
)
def test_unconfirmed_org_response_stops_after_one_write_without_clone(wire, response):
    router, runner, clone = wire
    router.post(ORIGIN + "orgs/team/repos").respond(200, json=response)

    result = runner.invoke(main, ["repo", "create", "team/sample", "--clone"])

    assert result.exit_code == 1
    assert "repository may have been created" in result.output
    assert "before retrying or pushing" in result.output
    assert "https://" not in result.output
    clone.assert_not_called()
    assert len(router.calls) == 1


@pytest.mark.parametrize(
    ("flags", "visibility"),
    [
        ([], {"public": 0}),
        (["--public"], {"private": False}),
        ([], {"private": True, "internal": True}),
        (["--public"], {"public": 1, "internal": 1}),
        ([], {"visibility": "private", "internal": None}),
        (["--public"], {"visibility": "public", "internal": "false"}),
        ([], {"private": 1, "internal": 0.0}),
        (["--public"], {"public": True, "internal": 2}),
        ([], {"private": True, "visibility": "internal"}),
        (["--public"], {"public": True, "private": "false"}),
    ],
)
def test_org_creation_requires_affirmative_visibility_without_internal_or_unknown_flags(wire, flags, visibility):
    router, runner, clone = wire
    router.post(ORIGIN + "orgs/team/repos").respond(200, json={"full_name": "team/sample", **visibility})

    result = runner.invoke(main, ["repo", "create", "team/sample", "--clone", *flags])

    assert result.exit_code == 1
    assert "repository may have been created" in result.output
    assert "before retrying or pushing" in result.output
    assert "No clone was attempted" in result.output
    assert "https://" not in result.output
    clone.assert_not_called()
    assert len(router.calls) == 1


@pytest.mark.parametrize(
    ("flags", "visibility"),
    [
        ([], {"visibility": "private"}),
        (["--public"], {"visibility": "public"}),
        ([], {"private": True, "internal": False}),
        (["--public"], {"public": 1, "internal": 0}),
    ],
)
def test_org_creation_accepts_exact_visibility_or_affirmative_flag(wire, flags, visibility):
    router, runner, clone = wire
    router.post(ORIGIN + "orgs/team/repos").respond(200, json={"full_name": "team/sample", **visibility})

    result = runner.invoke(main, ["repo", "create", "team/sample", *flags])

    assert result.exit_code == 0, result.output
    assert result.output == "https://gitcode.com/team/sample\n"
    clone.assert_not_called()
    assert len(router.calls) == 1


@pytest.mark.parametrize("status", [403, 422, 503])
def test_org_post_error_never_falls_back_to_personal_or_retries(wire, status):
    router, runner, clone = wire
    router.post(ORIGIN + "orgs/team/repos").mock(return_value=httpx.Response(status, json={"message": "unavailable"}))
    result = runner.invoke(main, ["repo", "create", "team/sample", "--clone"])
    assert result.exit_code != 0
    assert "Verify the remote state" in result.output
    clone.assert_not_called()
    assert len(router.calls) == 1
