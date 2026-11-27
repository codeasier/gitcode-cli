"""CLI contracts for generated source URLs (never attachment transfer URLs)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call

import pytest

from gitcode_cli.cli import main
from gitcode_cli.context import AppContext

REPO = "owner/repo"
BASE = f"/repos/{REPO}/releases"
ARCHIVE = f"https://gitcode.com/{REPO}/-/archive/v1/"
ZIP_NAME = "repo-v1.zip"
TAR_NAME = "repo-v1.tar.gz"
ZIP = {"name": ZIP_NAME, "browser_download_url": ARCHIVE + ZIP_NAME}
TAR = {"name": TAR_NAME, "browser_download_url": ARCHIVE + TAR_NAME, "type": "SOURCE"}
ATTACHMENT = {
    "name": "build.zip",
    "id": 7,
    "type": "ATTACH_FILE",
    "browser_download_url": "https://gitcode.com/owner/repo/releases/download/v1/build.zip?x=hidden",
}


@pytest.fixture
def harness(cli_runner, monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(AppContext, "client", lambda _: client)

    def run(*args, token="synthetic-no-network", repo=REPO):
        return cli_runner.invoke(main, ["--token", token, "release", *args, "-R", repo])

    return run, client


@pytest.mark.parametrize(
    ("tag_args", "get"),
    [(("v1",), call.get(BASE + "/tags/v1")), ((), call.get(BASE + "/latest", params={"type": "latest"}))],
)
def test_view_reads_tag_or_latest_once_and_projects_source_urls(harness, tag_args, get):
    run, client = harness
    client.get.return_value = {"tag_name": "v1", "assets": [TAR, ATTACHMENT, ZIP]}
    result = run("view", *tag_args, "--json", "tagName,zipballUrl,tarballUrl,assets")
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)
    assert list(row) == ["tagName", "zipballUrl", "tarballUrl", "assets"]
    assert row == {
        "tagName": "v1",
        "zipballUrl": ZIP["browser_download_url"],
        "tarballUrl": TAR["browser_download_url"],
        "assets": [{"name": "build.zip", "id": 7}],
    }
    assert client.mock_calls == [get, call.close()]


@pytest.mark.parametrize(
    ("tag_args", "get"),
    [(("v1",), call.get(BASE + "/tags/v1")), ((), call.get(BASE + "/latest", params={"type": "latest"}))],
)
def test_view_accepts_exact_lowercase_source_type(harness, tag_args, get):
    run, client = harness
    client.get.return_value = {
        "tag_name": "v1",
        "assets": [{**ZIP, "type": "source"}, {**TAR, "type": "source"}],
    }
    result = run("view", *tag_args, "--json", "tagName,zipballUrl,tarballUrl")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "tagName": "v1",
        "zipballUrl": ZIP["browser_download_url"],
        "tarballUrl": TAR["browser_download_url"],
    }
    assert client.mock_calls == [get, call.close()]


@pytest.mark.parametrize(
    "fields",
    [
        ("zipballUrl", "assets"),
        ("assets", "tarballUrl"),
        ("tagName", "zipballUrl", "tarballUrl", "assets"),
    ],
)
def test_view_mixed_source_and_assets_keep_attachments_only(harness, fields):
    run, client = harness
    other_archives = [
        {"name": name, "type": "source", "browser_download_url": ARCHIVE + name}
        for name in ("repo-v1.tar", "repo-v1.tar.bz2")
    ]
    client.get.return_value = {
        "tag_name": "v1",
        "assets": [
            {**TAR, "type": "source"},
            ATTACHMENT,
            {**ZIP, "type": "source"},
            *other_archives,
        ],
    }
    result = run("view", "v1", "--json", ",".join(fields))
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert list(output) == list(fields)
    expected = {
        "tagName": "v1",
        "zipballUrl": ZIP["browser_download_url"],
        "tarballUrl": TAR["browser_download_url"],
        "assets": [{"name": "build.zip", "id": 7}],
    }
    assert output == {field: expected[field] for field in fields}
    assert client.mock_calls == [call.get(BASE + "/tags/v1"), call.close()]


@pytest.mark.parametrize(
    "archives",
    [
        [{**ZIP, "type": "source", "browser_download_url": ARCHIVE + ZIP_NAME + "?credential=synthetic"}],
        [{**ZIP, "type": "source"}, {**ZIP, "name": ZIP_NAME.upper()}],
        [{"name": "repo-v1.7z", "type": "source", "browser_download_url": ARCHIVE + "repo-v1.7z"}],
    ],
)
def test_mixed_view_still_rejects_unconfirmed_type_source_rows(harness, archives):
    run, client = harness
    client.get.return_value = {"tag_name": "v1", "assets": [ATTACHMENT, *archives]}
    result = run("view", "v1", "--json", "zipballUrl,assets")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert client.mock_calls == [call.get(BASE + "/tags/v1"), call.close()]


def test_view_assets_only_does_not_change_legacy_type_validation(harness):
    run, client = harness
    client.get.return_value = {"tag_name": "v1", "assets": [{**ZIP, "type": "source"}, ATTACHMENT]}
    result = run("view", "v1", "--json", "assets")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert client.mock_calls == [call.get(BASE + "/tags/v1"), call.close()]


@pytest.mark.parametrize(
    "url",
    [
        ARCHIVE + ZIP_NAME + "?",
        ARCHIVE + ZIP_NAME + "?x=signed-storage",
        ARCHIVE + ZIP_NAME + "#",
        ARCHIVE + ZIP_NAME + "#anchor",
        "https://gitcode.com:443/owner/repo/-/archive/v1/" + ZIP_NAME,
        "https://gitcode.com.evil.invalid/owner/repo/-/archive/v1/" + ZIP_NAME,
        "https://secret@gitcode.com/owner/repo/-/archive/v1/" + ZIP_NAME,
        "http://gitcode.com/owner/repo/-/archive/v1/" + ZIP_NAME,
        "https://atomgit.com/owner/repo/-/archive/v1/" + ZIP_NAME,
        "https://gitcode.com/other/repo/-/archive/v1/" + ZIP_NAME,
        "https://gitcode.com/owner/repo/-/archive/v2/" + ZIP_NAME,
        "https://gitcode.com/owner/repo/-/archive/../v1/" + ZIP_NAME,
        "https://gitcode.com/owner/repo/-/archive/%761/" + ZIP_NAME,
        "https://gitcode.com/owner/repo/-/archive/v1/%72epo-v1.zip",
        "https://gitcode.com/owner/repo/releases/download/v1/" + ZIP_NAME,
        ARCHIVE + "different.zip",
        ARCHIVE + ZIP_NAME + "\n",
        None,
    ],
)
@pytest.mark.parametrize("kind", [None, "source"])
def test_unconfirmed_urls_are_not_projected(harness, url, kind):
    run, client = harness
    client.get.return_value = {"tag_name": "v1", "assets": [{**ZIP, "browser_download_url": url, "type": kind}, TAR]}
    result = run("view", "v1", "--json", "zipballUrl,tarballUrl")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"zipballUrl": None, "tarballUrl": TAR["browser_download_url"]}
    assert client.mock_calls == [call.get(BASE + "/tags/v1"), call.close()]


@pytest.mark.parametrize(
    "assets",
    [
        None,
        [],
        [ZIP, ZIP],
        [ZIP, {**ZIP, "name": ZIP_NAME.upper()}],
        [{**ZIP, "type": "source"}, {**ZIP, "name": ZIP_NAME.upper()}],
        [{**ZIP, "type": "ATTACH_FILE"}, {**TAR, "type": "zip"}],
        [{**ZIP, "type": "Source"}, {**TAR, "type": "attach"}],
        [{**ZIP, "type": {"format": "zip"}}],
        [{"name": "repo-v1.tar", "browser_download_url": ARCHIVE + "repo-v1.tar"}],
        [{"name": "repo-v1.tar.bz2", "browser_download_url": ARCHIVE + "repo-v1.tar.bz2"}],
        [ATTACHMENT],
    ],
)
def test_absent_ambiguous_or_non_source_metadata_produces_null(harness, assets):
    run, client = harness
    client.get.return_value = {"tag_name": "v1", "name": "v1 Release", "assets": assets}
    result = run("view", "v1", "--json", "name,zipballUrl,tarballUrl")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"name": "v1 Release", "zipballUrl": None, "tarballUrl": None}


@pytest.mark.parametrize(("repo", "tag"), [(REPO, "feature/v1"), (REPO, "v1..x"), ("owner/répô", "v1")])
def test_unverified_encoded_or_nonsimple_identities_stay_null(harness, repo, tag):
    run, client = harness
    name = f"{repo.split('/')[1]}-{tag}.zip"
    client.get.return_value = {
        "tag_name": tag,
        "assets": [{"name": name, "browser_download_url": f"https://gitcode.com/{repo}/-/archive/{tag}/{name}"}],
    }
    result = run("view", tag, "--json", "zipballUrl", repo=repo)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"zipballUrl": None}


def test_reflected_token_never_becomes_a_source_url(harness):
    run, client = harness
    token = "fixture-reflected-secret"
    name = f"repo-{token}.zip"
    client.get.return_value = {
        "tag_name": token,
        "assets": [{"name": name, "browser_download_url": f"https://gitcode.com/{REPO}/-/archive/{token}/{name}"}],
    }
    result = run("view", "--json", "zipballUrl", token=token)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"zipballUrl": None}
    assert token not in result.output


def test_archive_format_fields_are_view_only_and_opt_in(harness):
    run, client = harness
    result = run("list", "--json", "zipballUrl")
    assert result.exit_code == 2 and client.mock_calls == []
    assert "zipballUrl" not in run("list", "--help").output
    assert "zipballUrl" in run("view", "--help").output
    client.get.return_value = {"tag_name": "v1", "name": "stable", "assets": [TAR, ZIP]}
    result = run("view", "v1")
    assert result.exit_code == 0 and ARCHIVE not in result.output
    result = run("view", "v1", "--json", "zipballUrl", "--template", "{{.zipballUrl}}")
    assert result.exit_code == 0 and result.output.strip() == ZIP["browser_download_url"]
