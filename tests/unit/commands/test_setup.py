from __future__ import annotations

import json
import os

from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.commands.setup import shell_profile


def _env(tmp_path):
    return {
        "GC_GH_PROXY_DIR": str(tmp_path / "proxy"),
        "GC_GH_SHELL_PROFILE": str(tmp_path / ".zshenv"),
        "GC_OPENCODE_CONFIG": str(tmp_path / "opencode" / "opencode.json"),
    }


def test_gh_proxy_print_path(tmp_path):
    env = _env(tmp_path)
    result = CliRunner().invoke(main, ["setup", "gh-proxy", "--print-path"], env=env)
    assert result.exit_code == 0
    assert result.output.strip() == env["GC_GH_PROXY_DIR"]
    assert not (tmp_path / "proxy" / "gh").exists()


def test_install_and_uninstall_gh_proxy(tmp_path):
    runner = CliRunner()
    env = _env(tmp_path)
    installed = runner.invoke(main, ["setup", "gh-proxy"], env=env)
    shim = tmp_path / "proxy" / ("gh.cmd" if os.name == "nt" else "gh")
    assert installed.exit_code == 0, installed.output
    assert shim.exists()
    assert "gitcode_cli.gh_proxy" in shim.read_text(encoding="utf-8")
    if os.name != "nt":
        assert os.access(shim, os.X_OK)

    removed = runner.invoke(main, ["setup", "gh-proxy", "--uninstall"], env=env)
    assert removed.exit_code == 0, removed.output
    assert not shim.exists()


def test_uninstall_removes_shim_before_cleaning_malformed_profile(tmp_path):
    runner = CliRunner()
    env = _env(tmp_path)
    installed = runner.invoke(main, ["setup", "gh-proxy"], env=env)
    assert installed.exit_code == 0, installed.output
    shim = tmp_path / "proxy" / ("gh.cmd" if os.name == "nt" else "gh")
    (tmp_path / ".zshenv").write_text("# >>> gc gh-proxy >>>\n", encoding="utf-8")

    removed = runner.invoke(main, ["setup", "gh-proxy", "--uninstall"], env=env)

    assert removed.exit_code != 0
    assert "Malformed gc gh-proxy block" in removed.output
    assert not shim.exists()


def test_shell_profile_uses_bash_profile_on_macos(tmp_path, monkeypatch):
    monkeypatch.delenv("GC_GH_SHELL_PROFILE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr("gitcode_cli.commands.setup.sys.platform", "darwin")

    assert shell_profile() == tmp_path / ".bash_profile"


def test_install_refuses_to_overwrite_unmanaged_file(tmp_path):
    env = _env(tmp_path)
    shim = tmp_path / "proxy" / ("gh.cmd" if os.name == "nt" else "gh")
    shim.parent.mkdir()
    shim.write_text("native gh", encoding="utf-8")
    result = CliRunner().invoke(main, ["setup", "gh-proxy"], env=env)
    assert result.exit_code != 0
    assert "Refusing to overwrite unmanaged file" in result.output
    assert shim.read_text(encoding="utf-8") == "native gh"


def test_uninstall_refuses_to_remove_unmanaged_file(tmp_path):
    env = _env(tmp_path)
    shim = tmp_path / "proxy" / ("gh.cmd" if os.name == "nt" else "gh")
    shim.parent.mkdir()
    shim.write_text("native gh", encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["setup", "gh-proxy", "--uninstall"],
        env=env,
    )
    assert result.exit_code != 0
    assert "Refusing to remove unmanaged file" in result.output


def test_print_path_and_uninstall_are_mutually_exclusive(tmp_path):
    result = CliRunner().invoke(
        main,
        ["setup", "gh-proxy", "--print-path", "--uninstall"],
        env=_env(tmp_path),
    )
    assert result.exit_code != 0
    assert "cannot be used together" in result.output


def test_configure_and_uninstall_manage_shell_and_opencode(tmp_path):
    runner = CliRunner()
    env = _env(tmp_path)
    profile = tmp_path / ".zshenv"
    profile.write_text('eval "$(brew shellenv)"\n', encoding="utf-8")
    config_path = tmp_path / "opencode" / "opencode.json"
    config_path.parent.mkdir()
    config_path.write_text('{"$schema":"https://opencode.ai/config.json","model":"example/model"}\n')

    configured = runner.invoke(main, ["setup", "gh-proxy", "--configure"], env=env)
    assert configured.exit_code == 0, configured.output
    assert "Restart OpenCode" in configured.output
    profile_text = profile.read_text(encoding="utf-8")
    assert profile_text.count("# >>> gc gh-proxy >>>") == 1
    assert str(tmp_path / "proxy") in profile_text
    config = json.loads(config_path.read_text(encoding="utf-8"))
    instruction_ref = str(config_path.parent / "gh-proxy-instructions.md")
    assert config["model"] == "example/model"
    assert instruction_ref in config["instructions"]
    instructions = (config_path.parent / "gh-proxy-instructions.md").read_text(encoding="utf-8")
    assert "Use `gh` first" in instructions
    assert "Do not set `GH_HOST=gitcode.com`" in instructions

    configured_again = runner.invoke(main, ["setup", "gh-proxy", "--configure"], env=env)
    assert configured_again.exit_code == 0, configured_again.output
    assert profile.read_text(encoding="utf-8").count("# >>> gc gh-proxy >>>") == 1
    assert json.loads(config_path.read_text(encoding="utf-8"))["instructions"].count(instruction_ref) == 1

    removed = runner.invoke(main, ["setup", "gh-proxy", "--uninstall"], env=env)
    assert removed.exit_code == 0, removed.output
    assert "# >>> gc gh-proxy >>>" not in profile.read_text(encoding="utf-8")
    assert not (config_path.parent / "gh-proxy-instructions.md").exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["model"] == "example/model"
    assert instruction_ref not in config["instructions"]
