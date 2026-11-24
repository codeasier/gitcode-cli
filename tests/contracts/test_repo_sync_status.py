"""Direct CLI contract: no credentials, external network, local Git lookups or PUT."""

from __future__ import annotations

import inspect
import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from gitcode_cli import repo_read
from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

TOKEN = "synthetic-sync-token"
ORIGIN = "https://status.invalid/api/v5/"
URL = ORIGIN + "repos/Org/Fork_1/sync_repo"
BRANCH = "release/版本#%2F"
ARGS = ["repo", "sync-status", "Org/Fork_1", "-b", BRANCH]


def runner():
    # Click 8.1 combines streams by default; 8.2+ always captures them separately.
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


def run(*args):
    return runner().invoke(main, ["--token", TOKEN, *args])


@pytest.fixture
def router(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("sync-status must not read ambient credentials, local Git, a default, or other APIs")

    monkeypatch.setattr("gitcode_cli.cli.get_token", reject)
    monkeypatch.setattr("gitcode_cli.config.load_config", reject)
    monkeypatch.setattr("gitcode_cli.commands.repo._origin_repository_arg", reject)
    monkeypatch.setattr("gitcode_cli.commands.repo.configured_target", reject)
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", reject)
    monkeypatch.setattr(repo_read, "BASE_URL", ORIGIN)
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as routes:
        yield routes


@pytest.mark.parametrize("value,message", [(True, "已更新。"), (False, "Waiting for upstream."), (False, "")])
def test_one_get_with_only_explicit_branch(router, value, message):
    def handle(req):
        assert req.url.params.multi_items() == [("branch", BRANCH)]
        assert req.url.host == "status.invalid"
        assert req.url.raw_path.split(b"?")[0] == b"/api/v5/repos/Org/Fork_1/sync_repo"
        assert req.headers["Authorization"] == f"Bearer {TOKEN}"
        assert "private-token" not in req.headers and TOKEN not in str(req.url)
        assert req.headers["accept-encoding"] == "identity" and not req.content
        return httpx.Response(200, json={"repo_sync_result": value, "repo_sync_message": message, "extra": TOKEN})

    router.get(URL).mock(side_effect=handle)
    result = run(*ARGS)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"repo_sync_result": value, "repo_sync_message": message}
    assert TOKEN not in result.stdout and TOKEN not in result.stderr and len(router.calls) == 1


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("message_fields", [{}, {"repo_sync_message": None}], ids=["omitted", "null"])
def test_optional_provider_message_preserves_result_and_output_shape(router, value, message_fields):
    def handle(req):
        assert req.url.params.multi_items() == [("branch", BRANCH)]
        assert req.headers["Authorization"] == f"Bearer {TOKEN}"
        assert "private-token" not in req.headers and TOKEN not in str(req.url)
        assert not req.content
        return httpx.Response(200, json={"repo_sync_result": value, **message_fields})

    router.get(URL).mock(side_effect=handle)
    result = run(*ARGS)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"repo_sync_result": value, "repo_sync_message": None}
    assert not result.stderr and len(router.calls) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["repo", "sync-status"],
        ["repo", "sync-status", "o/r"],
        ["repo", "sync-status", "o/r", "-b", ""],
        ["repo", "sync-status", "o/r", "-b", "main", "--branch", "stable"],
        ["-R", "", *ARGS],
        ["-R", "Org/Fork_1", *ARGS],
        ["-R", "elsewhere/repo", *ARGS],
        [*ARGS, "-R", "Org/Fork_1"],
        [*ARGS, "--force"],
        [*ARGS, "--source", "upstream/source"],
    ],
)
def test_missing_or_ambiguous_input_is_not_inferred(router, args):
    result = run(*args)
    assert result.exit_code != 0 and not result.stdout and result.stderr and not router.calls


@pytest.mark.parametrize(
    "target",
    [
        "",
        "o",
        "/r",
        "o/",
        "o//r",
        "o/../r",
        "../r",
        "o/r#x",
        "o/r?key",
        "o/%2F",
        "o/r\\x",
        " o/r",
        "o/r ",
        "github.com/o/r",
        "gitcode.com/o/r",
        "https://gitcode.com/o/r",
        "o/r\u202e",
        "o/" + TOKEN,
        "o/" + "n" * 256,
    ],
)
def test_rejects_noncanonical_target_before_request(router, target):
    result = run("repo", "sync-status", target, "-b", "main")
    assert result.exit_code != 0 and not result.stdout and result.stderr and not router.calls
    assert TOKEN not in result.stdout and TOKEN not in result.stderr


@pytest.mark.parametrize(
    "branch",
    [
        " ",
        ".",
        "..",
        "topic/..",
        "a//b",
        "a/b.lock",
        "@",
        "HEAD",
        "refs/tags/v1",
        "x~2",
        "HEAD^",
        "-x",
        "a:b",
        "foo*bar",
        "x?[ab]",
        "a b",
        "a\n",
        "a\x1b",
        "try\u202e",
        TOKEN,
        "x" * 1025,
    ],
)
def test_rejects_unsafe_or_ambiguous_ref_before_request(router, branch):
    result = run("repo", "sync-status", "Org/Fork_1", "-b", branch)
    assert result.exit_code != 0 and not result.stdout and result.stderr and not router.calls
    assert TOKEN not in result.stdout and TOKEN not in result.stderr


def test_no_ambient_or_anonymous_fallback(router, monkeypatch):
    monkeypatch.setattr("gitcode_cli.cli.get_token", lambda: None)
    result = runner().invoke(main, ARGS)
    assert result.exit_code == 1 and "requires authentication" in result.stderr and not router.calls
    assert not result.stdout


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not JSON",
        b"null",
        b"[]",
        b"{}",
        b'{"events":[],"has_next_page":false}',
        b'{"repo_sync_result":null}',
        b'{"repo_sync_result":true,"repo_sync_message":false}',
        b'{"repo_sync_result":true,"repo_sync_message":0}',
        b'{"repo_sync_result":true,"repo_sync_message":[]}',
        b'{"repo_sync_result":true,"repo_sync_message":{}}',
        b'{"repo_sync_result":1,"repo_sync_message":"ok"}',
        b'{"repo_sync_result":"true","repo_sync_message":"ok"}',
        b'{"repo_sync_result":true,"repo_sync_result":false,"repo_sync_message":"ok"}',
        b'{"repo_sync_result":true,"repo_sync_message":null,"repo_sync_message":"ok"}',
    ],
)
def test_invalid_shape_or_duplicate_fields_fail_without_a_second_request(router, body):
    router.get(URL).respond(content=body)
    result = run(*ARGS)
    assert result.exit_code == 1 and "error:" in result.stderr and len(router.calls) == 1
    assert not result.stdout


@pytest.mark.parametrize("status", [202, 204, 302, 401, 403, 404, 429, 500])
def test_never_follows_redirects_or_retries(router, status):
    router.get(URL).respond(status, headers={"location": "https://elsewhere.invalid/sync_repo"}, content=TOKEN.encode())
    result = run(*ARGS)
    assert result.exit_code == 1 and f"HTTP {status}" in result.stderr
    assert not result.stdout
    assert TOKEN not in result.stdout and TOKEN not in result.stderr and len(router.calls) == 1


@pytest.mark.parametrize(
    "message",
    [
        f"failed {TOKEN}",
        "one\nrepo_sync_result: true",
        "Spelling\u202e",
        "x\x1b[1m",
        "x" * 513,
        "https://a.invalid/x?sig=secret",
        "Authorization: Bearer hidden",
        "access_token=hidden",
        "private-token: hidden",
    ],
)
def test_unsafe_provider_message_is_withheld_not_replayed(router, message):
    router.get(URL).respond(json={"repo_sync_result": False, "repo_sync_message": message})
    result = run(*ARGS)
    assert result.exit_code == 0 and json.loads(result.stdout) == {
        "repo_sync_result": False,
        "repo_sync_message": "[message withheld]",
    }
    assert message not in result.stdout and message not in result.stderr and len(router.calls) == 1


def test_oversize_body_fails_without_partial_output(router):
    router.get(URL).respond(content=b"x" * (repo_read.MAX_RESPONSE + 1))
    result = run(*ARGS)
    assert result.exit_code == 1 and "2 MiB" in result.stderr and not result.stdout and len(router.calls) == 1


def test_native_only_visible_command(router):
    assert "sync-status" in run("repo", "--help").stdout
    help_text = run("repo", "sync-status", "--help").stdout
    assert "without -R" in help_text
    assert "repo_sync_message string or null" in help_text
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(ARGS)
    assert not router.calls
