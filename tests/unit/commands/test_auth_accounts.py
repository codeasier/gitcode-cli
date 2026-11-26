"""Local account selection. All credential inputs are inert fixtures; no HTTP access."""

from __future__ import annotations

import json
import os
import stat
from unittest.mock import MagicMock

import pytest

from gitcode_cli import config
from gitcode_cli.cli import main
from gitcode_cli.errors import APIError, ConfigError


@pytest.fixture
def accounts_cli(tmp_config_dir, cli_runner, monkeypatch):
    monkeypatch.delenv("GC_TOKEN", raising=False)
    responses = {"fixture-A": {"login": "alice"}, "fixture-B": {"login": "bob"}, "fixture-L": {"login": "legacy-user"}}
    requests = []

    def client_for(ctx):
        client = MagicMock()

        def get(path):
            assert path == "/user" and ctx.token in responses
            requests.append(ctx.token)
            response = responses[ctx.token]
            if isinstance(response, Exception):
                raise response
            return response

        client.get.side_effect = get
        return client

    monkeypatch.setattr("gitcode_cli.context.AppContext.client", client_for)

    def run(*args, token=None, env=None, code=0):
        result = cli_runner.invoke(main, list(args), input=f"{token}\n" if token is not None else "", env=env)
        assert result.exit_code == code, (result.output, result.exception)
        if "token" not in args:
            for value in responses:
                assert value not in result.output
        return result.output

    return run, responses, requests


def test_login_hostname_keeps_named_verification_and_override_precedence(accounts_cli, monkeypatch):
    run, _, requests = accounts_cli
    monkeypatch.setenv("GC_TOKEN", "environment-override")
    output = run(
        "--token",
        "explicit-override",
        "auth",
        "login",
        "-h",
        "gitcode.com",
        "--account",
        "--with-token",
        token="fixture-A",
    )
    assert "--token still overrides" in output
    assert "explicit-override" not in output and "environment-override" not in output
    assert requests == ["fixture-A"]
    assert config.get_token("explicit-override") == "explicit-override"
    assert config.get_token() == "environment-override"
    monkeypatch.delenv("GC_TOKEN")
    assert config.get_token() == "fixture-A"
    assert config.load_config() == {"accounts": {"alice": "fixture-A"}, "active_account": "alice"}


def test_named_login_switch_legacy_roundtrip(accounts_cli):
    run, _, requests = accounts_cli
    config.save_config({"token": "fixture-L", "unrelated": ["kept"]})
    run("auth", "login", "--account", "--with-token", token="fixture-A", env={"GC_TOKEN": "ignored-input"})
    run("auth", "login", "--account", "--with-token", token="fixture-B")
    assert requests == ["fixture-A", "fixture-B"]
    assert config.get_token() == "fixture-B"
    assert config.load_config()["unrelated"] == ["kept"]
    assert "token" not in config.load_config()  # old binaries cannot fall back to legacy
    if os.name == "posix":
        assert stat.S_IMODE(config.CONFIG_PATH.stat().st_mode) == 0o600
        assert stat.S_IMODE(config.CONFIG_DIR.stat().st_mode) == 0o700

    assert "alice" in run("auth", "switch", "-u", "alice")
    assert run("auth", "token") == "fixture-A\n"
    assert run("auth", "token", "--user", "bob") == "fixture-B\n"
    run("auth", "logout", "-u", "bob")
    assert config.get_token() == "fixture-A"
    run("auth", "logout")
    assert "No active saved account" in run("auth", "token", code=1)
    assert "No saved account matches" in run("auth", "switch", "-u", "unknown", code=1)
    run("auth", "switch", "--legacy")
    assert config.load_config() == {"unrelated": ["kept"], "token": "fixture-L"}
    assert requests == ["fixture-A", "fixture-B"]


def test_unnamed_login_does_not_erase_profiles_and_relogin_replaces_only_that_account(accounts_cli):
    run, responses, requests = accounts_cli
    run("auth", "login", "--with-token", "--account", token="fixture-A")
    run("auth", "login", "--with-token", token="fixture-L")
    assert config.get_token() == "fixture-L"
    assert run("auth", "token", "-u", "alice").strip() == "fixture-A"
    responses["replacement"] = {"login": "alice"}
    run("auth", "login", "--with-token", "--account", token="replacement")
    assert config.load_config() == {
        "accounts": {"alice": "replacement", "@legacy": "fixture-L"},
        "active_account": "alice",
    }
    assert requests == ["fixture-A", "replacement"]


@pytest.mark.parametrize(
    "invalid", [{}, {"username": "name"}, {"login": "x\nunsafe"}, {"login": "fixture-X"}, APIError("fixture-X")]
)
def test_failed_verification_never_rewrites_config_or_prints_raw_response(accounts_cli, invalid):
    run, responses, _ = accounts_cli
    config.save_config({"token": "fixture-L"})
    before = config.CONFIG_PATH.read_bytes()
    responses["fixture-X"] = invalid
    output = run("auth", "login", "--account", "--with-token", token="fixture-X", code=1)
    assert "Unable to verify authentication" in output and "unsafe" not in output
    assert config.CONFIG_PATH.read_bytes() == before


def test_precedence_unknown_user_and_shadowed_edits_never_fall_back(accounts_cli):
    run, _, requests = accounts_cli
    config.save_config({"token": "fixture-L"})
    assert run("--token", "flag-input", "auth", "token", env={"GC_TOKEN": "environment-input"}).strip() == "flag-input"
    assert run("auth", "token", env={"GC_TOKEN": "environment-input"}).strip() == "environment-input"
    assert "No saved account matches" in run("auth", "token", "-u", "missing", code=1)
    for args in [["logout"], ["switch", "--legacy"], ["token", "-u", "@legacy"]]:
        output = run("auth", *args, env={"GC_TOKEN": "environment-input"}, code=1)
        assert "GC_TOKEN overrides saved accounts" in output and "environment-input" not in output
    assert config.load_config() == {"token": "fixture-L"}
    assert requests == []


def test_all_accounts_status_from_exact_tokens_and_active_filter(accounts_cli):
    run, responses, requests = accounts_cli
    config.save_config({"accounts": {"alice": "fixture-A", "bob": "fixture-B"}, "active_account": "bob"})
    assert "Saved account: alice" in run("auth", "status")
    assert requests == []  # no network in text mode
    entries = json.loads(run("auth", "status", "--json", "hosts"))["hosts"]["gitcode.com"]
    assert [(e["login"], e["active"], e["state"]) for e in entries] == [
        ("bob", True, "success"),
        ("alice", False, "success"),
    ]
    assert requests == ["fixture-B", "fixture-A"]
    requests.clear()
    assert "alice" not in run("auth", "status", "-a", "--json", "hosts")
    assert requests == ["fixture-B"]
    responses["fixture-B"] = {"login": "someone-else"}
    assert "no longer matches" in run("auth", "status", "-a", "--json", "hosts")
    requests.clear()
    assert "bob" not in run("auth", "status", "--json", "hosts", env={"GC_TOKEN": "fixture-L"})
    assert requests == ["fixture-L"]  # do not send unrelated local tokens for an override


def test_no_active_means_no_automatic_selection(accounts_cli):
    run, _, requests = accounts_cli
    config.save_config({"accounts": {"alice": "fixture-A", "bob": "fixture-B"}, "active_account": "alice"})
    run("auth", "logout")
    assert "No active saved account" in run("auth", "token", code=1)
    assert "No active saved account" in run("auth", "logout", code=1)
    assert "Not logged in" in run("auth", "status")
    assert json.loads(run("auth", "status", "--active", "--json", "hosts")) == {"hosts": {}}
    run("auth", "switch", code=2)
    run("auth", "switch", "--user", "bob", "--legacy", code=2)
    assert "No saved account matches" in run("auth", "switch", "--legacy", code=1)
    assert requests == []
    run("auth", "switch", "--user", "bob")
    assert config.get_token() == "fixture-B"


@pytest.mark.parametrize(
    "malformed",
    [
        [],
        {"accounts": {}, "active_account": "missing"},
        {"accounts": {}, "active_account": []},
        {"accounts": {}},
        {"token": "x", "accounts": {}, "active_account": None},
        {"token": {}},
        {"accounts": {"x\n": "fixture-A"}, "active_account": None},
    ],
)
def test_malformed_accounts_fail_without_mutation_or_value_leaks(accounts_cli, malformed):
    run, _, requests = accounts_cli
    before = json.dumps(malformed)
    config.CONFIG_PATH.write_text(before)
    assert "Invalid" in run("auth", "status", code=1)
    assert "Invalid" in run("auth", "login", "--with-token", token="fixture-L", code=1)
    assert config.CONFIG_PATH.read_text() == before
    assert not requests


def test_concurrent_updates_cannot_resurrect_or_drop_saved_credentials(accounts_cli):
    run, _, _ = accounts_cli
    config.save_config({"token": "fixture-L"})
    with config.edit_accounts():
        assert "locked" in run("auth", "logout", code=1)
    assert config.get_token() == "fixture-L"
    with pytest.raises(ConfigError, match="single"):
        with config.edit_accounts():
            raise ConfigError("single")
    assert list(config.CONFIG_DIR.iterdir()) == [config.CONFIG_PATH]


def test_multiline_token_is_not_saved(accounts_cli):
    run, _, requests = accounts_cli
    assert "Expected one non-empty token" in run(
        "auth", "login", "--with-token", "--account", token="line1\nline2", code=1
    )
    assert requests == []
    assert not config.CONFIG_PATH.exists()
