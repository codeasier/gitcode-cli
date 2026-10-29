"""Offline regression cases for issue #168's response and credential failures."""

import json
import logging
import os
import stat
from unittest.mock import MagicMock
from urllib.parse import quote

import httpx
import pytest

from gitcode_cli import config
from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient
from gitcode_cli.errors import APIError, ConfigError, NetworkError


@pytest.fixture(autouse=True)
def synthetic_auth(monkeypatch):
    monkeypatch.setenv("GC_TOKEN", "synthetic-failure-test-token")


@pytest.mark.parametrize("status", [100, 200, 201, 202, 205, 301, 302, 307, 308])
def test_unconfirmed_delete_is_not_success(status):
    client = GitCodeClient("synthetic-token")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    try:
        with pytest.raises(APIError):
            client.delete("/repos/owner/repo")
    finally:
        client.close()


def test_documented_repository_delete_accepts_json_object():
    client = GitCodeClient("synthetic-token")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
    try:
        assert client.delete("/repos/owner/repo") == {}
    finally:
        client.close()


@pytest.mark.parametrize("body", [b"", b"not json", b"null"])
def test_invalid_write_response_requires_verification(body):
    client = GitCodeClient("synthetic-token")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)))
    try:
        with pytest.raises(APIError, match="[Vv]erify.*retry"):
            client.put("/repos/owner/repo/pulls/1/merge")
    finally:
        client.close()


@pytest.mark.parametrize(
    "response", [{"merged": False, "message": "Merge refused"}, {"merged": "true"}, {}, None, [], {"merged": 0}]
)
def test_merge_without_positive_evidence_never_deletes(response, cli_runner, mock_app_context, monkeypatch):
    client = MagicMock()
    client.get.return_value = {"head": {"ref": "feature"}}
    client.put.return_value = response
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    run = MagicMock()
    monkeypatch.setattr("gitcode_cli.pr_git.subprocess.run", run)
    result = cli_runner.invoke(main, ["pr", "merge", "1", "-R", "owner/repo", "--delete-branch"])
    assert result.exit_code == 1
    assert "merge" in result.output.lower()
    assert not any(call.args[0][:2] == ["git", "push"] for call in run.call_args_list)


def test_config_is_private_even_with_permissive_umask(tmp_config_dir):
    old = os.umask(0o022)
    try:
        config.save_config({"token": "synthetic-token"})
    finally:
        os.umask(old)
    assert stat.S_IMODE(tmp_config_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(config.CONFIG_PATH.stat().st_mode) == 0o600
    assert config.load_config()["token"] == "synthetic-token"


@pytest.mark.parametrize("link_kind", ["file", "directory", "hardlink"])
def test_config_refuses_linked_storage(tmp_config_dir, tmp_path, link_kind):
    target = tmp_path / "unrelated"
    if link_kind == "directory":
        target.mkdir()
        tmp_config_dir.rmdir()
        tmp_config_dir.symlink_to(target, target_is_directory=True)
    else:
        target.write_text("original")
        if link_kind == "file":
            config.CONFIG_PATH.symlink_to(target)
        else:
            os.link(target, config.CONFIG_PATH)
    with pytest.raises(ConfigError):
        config.save_config({"token": "synthetic-token"})
    if link_kind != "directory":
        assert target.read_text() == "original"


def test_config_replace_failure_preserves_old_file_and_cleans_temp(tmp_config_dir, monkeypatch):
    config.save_config({"token": "original"})
    monkeypatch.setattr(os, "replace", MagicMock(side_effect=OSError("disk error")))
    with pytest.raises(ConfigError):
        config.save_config({"token": "replacement"})
    assert json.loads(config.CONFIG_PATH.read_text()) == {"token": "original"}
    assert list(tmp_config_dir.iterdir()) == [config.CONFIG_PATH]


def test_httpx_logging_and_errors_redact_token(caplog):
    token = "synthetic/secret+value"
    client = GitCodeClient(token)
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json={"message": f"bad token {token}"}))
    )
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(APIError) as exc:
            client.get("/user")
        for text in (caplog.text, str(exc.value)):
            assert token not in text
            assert quote(token, safe="") not in text
        assert "HTTP Request" in caplog.text
    finally:
        client.close()


def test_network_error_is_redacted_and_write_is_uncertain():
    token = "synthetic-secret"
    client = GitCodeClient(token)
    client._client.close()
    client._client = MagicMock()
    client._client.request.side_effect = httpx.ReadTimeout(f"timeout access_token={token}")
    with pytest.raises(NetworkError, match="[Vv]erify.*retry") as exc:
        client.post("/repos/owner/issues", json={"title": "hello"})
    assert token not in str(exc.value)
