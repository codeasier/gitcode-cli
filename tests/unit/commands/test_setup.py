from __future__ import annotations

import os

from click.testing import CliRunner

from gitcode_cli.cli import main


def test_gh_proxy_print_path(tmp_path):
    result = CliRunner().invoke(main, ["setup", "gh-proxy", "--print-path"], env={"GC_GH_PROXY_DIR": str(tmp_path)})
    assert result.exit_code == 0
    assert result.output.strip() == str(tmp_path)
    assert not (tmp_path / "gh").exists()


def test_install_and_uninstall_gh_proxy(tmp_path):
    runner = CliRunner()
    env = {"GC_GH_PROXY_DIR": str(tmp_path)}
    installed = runner.invoke(main, ["setup", "gh-proxy"], env=env)
    shim = tmp_path / ("gh.cmd" if os.name == "nt" else "gh")
    assert installed.exit_code == 0, installed.output
    assert shim.exists()
    assert "gitcode_cli.gh_proxy" in shim.read_text(encoding="utf-8")
    if os.name != "nt":
        assert os.access(shim, os.X_OK)

    removed = runner.invoke(main, ["setup", "gh-proxy", "--uninstall"], env=env)
    assert removed.exit_code == 0, removed.output
    assert not shim.exists()


def test_install_refuses_to_overwrite_unmanaged_file(tmp_path):
    shim = tmp_path / ("gh.cmd" if os.name == "nt" else "gh")
    shim.write_text("native gh", encoding="utf-8")
    result = CliRunner().invoke(main, ["setup", "gh-proxy"], env={"GC_GH_PROXY_DIR": str(tmp_path)})
    assert result.exit_code != 0
    assert "Refusing to overwrite unmanaged file" in result.output
    assert shim.read_text(encoding="utf-8") == "native gh"


def test_uninstall_refuses_to_remove_unmanaged_file(tmp_path):
    shim = tmp_path / ("gh.cmd" if os.name == "nt" else "gh")
    shim.write_text("native gh", encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["setup", "gh-proxy", "--uninstall"],
        env={"GC_GH_PROXY_DIR": str(tmp_path)},
    )
    assert result.exit_code != 0
    assert "Refusing to remove unmanaged file" in result.output


def test_print_path_and_uninstall_are_mutually_exclusive(tmp_path):
    result = CliRunner().invoke(
        main,
        ["setup", "gh-proxy", "--print-path", "--uninstall"],
        env={"GC_GH_PROXY_DIR": str(tmp_path)},
    )
    assert result.exit_code != 0
    assert "cannot be used together" in result.output
