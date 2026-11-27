from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.errors import APIError, NetworkError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def separate_stream_runner():
    # Click 8.0/8.1 mix stderr into stdout by default; 8.2+ always
    # captures both separately and removed the mix_stderr constructor option.
    kwargs = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
    return CliRunner(**kwargs)


class TestAuthLogin:
    @pytest.mark.parametrize("selector", [["--hostname", "gitcode.com"], ["--hostname=GitCode.COM"], ["-hgitcode.com"]])
    def test_login_hostname_accepts_single_host_for_legacy_slot(self, runner, tmp_config_dir, selector):
        result = runner.invoke(main, ["auth", "login", *selector, "--with-token"], input="fixture-host-only\n")
        assert result.exit_code == 0, result.output
        assert json.loads((tmp_config_dir / "config.json").read_text()) == {"token": "fixture-host-only"}
        assert "fixture-host-only" not in result.output

    @pytest.mark.parametrize("with_token", [False, True])
    @pytest.mark.parametrize(
        "selector",
        [
            ["--hostname="],
            ["-h", "github.com"],
            ["-h", "gitcode.com."],
            ["--hostname", "ssh.gitcode.com"],
            ["--hostname", "gitcode.com:443"],
            ["--hostname", "https://userinfo@gitcode.com/sensitive-path"],
            ["--hostname", " gitcode.com"],
            ["-h", "elsewhere.invalid", "--hostname=gitcode.com"],
        ],
    )
    def test_login_rejects_host_before_credential_use(
        self, separate_stream_runner, tmp_config_dir, monkeypatch, selector, with_token
    ):
        config_path = tmp_config_dir / "config.json"
        original = b'{"token":"inert-existing-fixture"}'
        config_path.write_bytes(original)
        mock_sys = MagicMock()
        monkeypatch.setattr("gitcode_cli.commands.auth.sys", mock_sys)
        prompt = MagicMock()
        monkeypatch.setattr("click.prompt", prompt)
        verify = MagicMock()
        monkeypatch.setattr("gitcode_cli.commands.auth._verified_login", verify)
        result = separate_stream_runner.invoke(
            main, ["auth", "login", "--account", *selector, *(["--with-token"] if with_token else [])]
        )
        assert result.exit_code == 2
        assert result.stdout == ""
        assert "Only gitcode.com is supported" in result.stderr
        assert "sensitive-path" not in result.stderr and "userinfo" not in result.stderr
        mock_sys.stdin.read.assert_not_called()
        prompt.assert_not_called()
        verify.assert_not_called()
        assert config_path.read_bytes() == original

    def test_login_short_host_requires_value_and_long_help_still_works(self, runner, tmp_config_dir):
        missing = runner.invoke(main, ["auth", "login", "-h"])
        assert missing.exit_code == 2
        help_result = runner.invoke(main, ["auth", "login", "--help"])
        assert help_result.exit_code == 0
        assert "--hostname" in help_result.output and "--with-token" in help_result.output
        assert not (tmp_config_dir / "config.json").exists()

    def test_auth_login_prompt(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login"], input="mytoken\n")
        assert result.exit_code == 0
        assert "Authentication saved." in result.output
        config_path = tmp_config_dir / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["token"] == "mytoken"

    def test_auth_login_with_token_reads_from_stdin_without_prompting(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login", "--with-token"], input="mytoken\n")
        assert result.exit_code == 0
        assert "GitCode token" not in result.output
        assert "Authentication saved." in result.output
        config_path = tmp_config_dir / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["token"] == "mytoken"

    def test_auth_login_with_token_rejects_blank_stdin(self, runner, tmp_config_dir):
        result = runner.invoke(main, ["auth", "login", "--with-token"], input="\n")
        assert result.exit_code != 0
        assert "No token provided on stdin." in result.output
        config_path = tmp_config_dir / "config.json"
        assert not config_path.exists()


class TestAuthStatus:
    def test_status_reports_gh_proxy_target(self, runner, tmp_config_dir, monkeypatch):
        monkeypatch.setenv("GC_TOKEN", "synthetic-value")
        result = runner.invoke(main, ["auth", "status"], env={"GC_GH_PROXY_ACTIVE": "1"})
        assert result.exit_code == 0
        assert "gitcode.com" in result.output
        assert "✓ Logged in to GitCode" in result.output
        assert "Active account: true" in result.output
        assert "API host: https://api.gitcode.com" in result.output
        assert "Token source: GC_TOKEN" in result.output
        assert "synthetic" not in result.output
        assert "gh proxy: active; commands target GitCode, not GitHub" in result.output

    def test_status_reports_missing_auth_and_proxy_target(self, runner, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("GC_TOKEN", raising=False)
        result = runner.invoke(main, ["auth", "status"], env={"GC_GH_PROXY_ACTIVE": "1"})
        assert result.exit_code == 1
        assert "X Not logged in to GitCode" in result.output
        assert "gh proxy: active; commands target GitCode, not GitHub" in result.output

    def test_status_preserves_gc_exit_code_when_auth_is_missing(self, runner, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("GC_TOKEN", raising=False)
        result = runner.invoke(main, ["auth", "status"])
        assert result.exit_code == 0


class TestStructuredAuthStatus:
    @pytest.fixture
    def client(self, monkeypatch, tmp_config_dir):
        monkeypatch.delenv("GC_TOKEN", raising=False)
        client = MagicMock()
        client.get.return_value = {"login": "alice", "token": "must-not-export-user-payload"}
        monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
        return client

    def test_json_verifies_user_without_exporting_credentials(self, runner, client, tmp_config_dir):
        token = "synthetic-auth-status-secret"
        (tmp_config_dir / "config.json").write_text(json.dumps({"token": token}))
        result = runner.invoke(main, ["auth", "status", "--json", "hosts"], env={"GC_GH_PROXY_ACTIVE": "1"})

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {
            "hosts": {
                "gitcode.com": [
                    {
                        "host": "gitcode.com",
                        "active": True,
                        "tokenSource": str(tmp_config_dir / "config.json"),
                        "login": "alice",
                        "state": "success",
                    }
                ]
            }
        }
        client.get.assert_called_once_with("/user")
        assert token not in result.output
        assert "must-not-export-user-payload" not in result.output

    @pytest.mark.parametrize(
        ("explicit_token", "env_token", "expected_source"),
        [(None, "env-secret", "GC_TOKEN"), ("flag-secret", "env-secret", "--token")],
    )
    def test_json_uses_cli_token_precedence(self, runner, client, explicit_token, env_token, expected_source):
        args = ["--token", explicit_token] if explicit_token else []
        result = runner.invoke(main, [*args, "auth", "status", "--json", "hosts"], env={"GC_TOKEN": env_token})

        assert result.exit_code == 0, result.output
        entry = json.loads(result.output)["hosts"]["gitcode.com"][0]
        assert entry["tokenSource"] == expected_source
        assert env_token not in result.output
        assert explicit_token is None or explicit_token not in result.output

    def test_json_missing_auth_is_empty_and_successful_even_under_proxy(self, runner, client):
        result = runner.invoke(main, ["auth", "status", "--json", "hosts"], env={"GC_GH_PROXY_ACTIVE": "1"})

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {"hosts": {}}
        client.get.assert_not_called()

    @pytest.mark.parametrize(
        "response",
        [APIError("upstream echoed synthetic-secret", status_code=401), NetworkError("synthetic-secret"), {}, None],
    )
    def test_json_reports_unverifiable_auth_without_leaking_diagnostics(self, runner, client, response):
        if isinstance(response, Exception):
            client.get.side_effect = response
        else:
            client.get.return_value = response
        result = runner.invoke(main, ["--token", "synthetic-secret", "auth", "status", "--json", "hosts"])

        assert result.exit_code == 0, result.output
        entry = json.loads(result.output)["hosts"]["gitcode.com"][0]
        assert entry["state"] == "error"
        assert "Unable to verify" in entry["error"]
        assert "synthetic-secret" not in result.output

    def test_json_malformed_config_fails(self, runner, client, tmp_config_dir):
        (tmp_config_dir / "config.json").write_text("{malformed")
        result = runner.invoke(main, ["auth", "status", "--json", "hosts"])

        assert result.exit_code == 1
        assert "Invalid config file" in result.output
        client.get.assert_not_called()

    def test_json_jq_filters_hosts(self, runner, client):
        result = runner.invoke(
            main,
            [
                "--token",
                "synthetic-secret",
                "auth",
                "status",
                "--json",
                "hosts",
                "--jq",
                '.hosts["gitcode.com"][0].login',
            ],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == "alice"

    def test_json_template_uses_shared_formatter(self, runner, client):
        result = runner.invoke(
            main, ["--token", "synthetic-secret", "auth", "status", "--json", "hosts", "--template", "{{.hosts}}"]
        )

        assert result.exit_code == 0, result.output
        assert "gitcode.com" in result.output
        assert "alice" in result.output
        assert "synthetic-secret" not in result.output

    @pytest.mark.parametrize(
        "options",
        [
            ["--json"],
            ["--json", "token"],
            ["--jq", ".hosts"],
            ["--template", "{{.hosts}}"],
            ["--json", "hosts", "--jq", ".hosts", "--template", "{{.hosts}}"],
        ],
    )
    def test_invalid_output_options_fail_before_api(self, runner, client, options):
        result = runner.invoke(main, ["--token", "synthetic-secret", "auth", "status", *options])

        assert result.exit_code == 2, result.output
        client.get.assert_not_called()

    def test_help_lists_json_fields(self, runner, client):
        result = runner.invoke(main, ["auth", "status", "--help"])

        assert result.exit_code == 0
        assert "JSON FIELDS\n  hosts" in result.output
        client.get.assert_not_called()
