"""CLI contracts for real GitCode Release attachment metadata shapes."""

from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.context import AppContext

REPO = "owner/repo"
BASE = f"/repos/{REPO}/releases"


@pytest.fixture
def harness(monkeypatch):
    # Click < 8.2 mixes stderr into stdout unless explicitly disabled.
    params = inspect.signature(CliRunner.__init__).parameters
    cli_runner = CliRunner(mix_stderr=False) if "mix_stderr" in params else CliRunner()
    client = MagicMock()
    monkeypatch.setattr(AppContext, "client", lambda _: client)

    def run(*args, token="synthetic-no-network", repo=REPO):
        return cli_runner.invoke(main, ["--token", token, "release", *args, "-R", repo])

    return run, client


@pytest.mark.parametrize("tag_args", [("v1",), ()])
def test_observed_gitcode_source_and_attach_project_only_ordinary_attachment(harness, tag_args):
    run, client = harness
    raw = f"https://raw.gitcode.com/{REPO}/archive/refs/heads"
    sources = [
        {"type": "source", "name": f"v1.{suffix}", "browser_download_url": f"{raw}/v1.{suffix}"}
        for suffix in ("zip", "tar.gz", "tar.bz2", "tar")
    ]
    attachment = {
        "type": "attach",
        "name": "build.zip",
        "id": 23,
        "size": 100,
        "browser_download_url": f"https://gitcode.com/{REPO}/releases/download/v1/build.zip",
    }
    row = {"tag_name": "v1", "assets": [*sources, attachment]}
    client.get.return_value = row
    only_assets = run("view", *tag_args, "--json", "tagName,assets")
    assert only_assets.exit_code == 0, only_assets.output
    assert json.loads(only_assets.output)["assets"] == [{"name": "build.zip", "id": 23, "size": 100}]
    client.get.return_value = [row]
    listed = run("list", "--json", "tagName,assets")
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output) == [{"tagName": "v1", "assets": [{"name": "build.zip", "id": 23, "size": 100}]}]


@pytest.mark.parametrize(
    "url",
    [
        "https://raw.gitcode.com/other/repo/archive/refs/heads/v1.zip",
        "https://raw.gitcode.com/owner/repo/archive/refs/heads/v2.zip",
        "https://raw.gitcode.com/owner/repo/archive/refs/heads/v1.zip?signature=private",
        "https://gitcode.com/owner/repo/releases/download/v1/v1.zip",
    ],
)
def test_observed_raw_source_projection_rejects_mismatched_route(harness, url):
    run, client = harness
    client.get.return_value = {
        "tag_name": "v1",
        "assets": [{"type": "source", "name": "v1.zip", "browser_download_url": url}],
    }
    result = run("view", "v1", "--json", "tagName,assets")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert url not in result.stderr
