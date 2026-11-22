"""Offline command, wire-contract and isolated binary-stream checks."""

from __future__ import annotations

import hashlib
import io
import json
import os
from email.message import Message
from unittest.mock import MagicMock, call
from urllib.error import HTTPError

import pytest
from click.testing import CliRunner

from gitcode_cli import release_assets as binary
from gitcode_cli import release_files as local
from gitcode_cli.commands import release as cmd
from gitcode_cli.context import AppContext
from gitcode_cli.errors import APIError, GCError
from gitcode_cli.services.releases import ReleaseService, release_record, tag_segment

BASE = "/repos/o/r/releases"
STORAGE = "https://object.obs.cn-south-1.myhuaweicloud.com/data?Signature=synthetic"
RAW = "https://gitcode.com/o/r/-/releases/v1/downloads/"
HEADER = {
    "Content-Type": "application/octet-stream",
    "x-obs-meta-project-id": "42",
    "x-obs-acl": "private",
    "x-obs-callback": "synthetic",
}
posix_files = pytest.mark.skipif(os.name != "posix", reason="requires secure POSIX file access")
DATA = b"\x00\xfd\xe8\n"
SHA = hashlib.sha256(DATA).hexdigest()
FILE = {
    "name": "build.zip",
    "type": "ATTACH_FILE",
    "id": 4,
    "browser_download_url": RAW + "build.zip",
    "size": len(DATA),
    "digest": "sha256:" + SHA,
}
ARCH = {"name": "r-v1.zip", "browser_download_url": "https://gitcode.com/o/r/-/archive/v1/r-v1.zip"}
ROW = {
    "name": "Release",
    "body": "Notes",
    "tag_name": "v1",
    "assets": [ARCH, FILE],
    "prerelease": False,
    "release_status": "latest",
}


class Response(io.BytesIO):
    def __init__(self, data=DATA, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


@pytest.fixture
def tmp_path(tmp_path):
    # The platform’s temp aliases (e.g. /var on macOS) are intentional, but
    # the CLI itself must never resolve user-supplied link components.
    return tmp_path.resolve()


@pytest.fixture
def harness(monkeypatch):
    client = MagicMock(token="offline-api-key")
    monkeypatch.setattr(AppContext, "client", lambda _: client)

    def run(*args, stdin=None):
        return CliRunner().invoke(cmd.release_group, args, input=stdin, obj={"app": AppContext("synthetic", "o/r")})

    return run, client


def test_list_view_and_browser(harness, monkeypatch):
    run, client = harness
    client.get.return_value = [ROW]
    out = run("list", "--json", "tagName,isLatest,assets", "-L", "1")
    assert out.exit_code == 0, out.exception
    parsed = json.loads(out.output)
    assert parsed[0]["tagName"] == "v1" and parsed[0]["isLatest"] is True
    assert parsed[0]["assets"] == [{"id": 4, "name": "build.zip", "size": len(DATA), "digest": "sha256:" + SHA}]
    client.get.assert_called_once_with(BASE, params={"page": 1, "per_page": 1, "direction": "desc"})
    client.get.return_value = ROW
    assert "Notes" in run("view").output
    client.get.assert_called_with(BASE + "/latest", params={"type": "latest"})
    client.get.return_value = {**ROW, "tag_name": "latest"}
    browser = MagicMock()
    monkeypatch.setattr(cmd, "open_in_browser", browser)
    assert run("view", "latest", "--web").exit_code == 0
    client.get.assert_called_with(BASE + "/tags/latest")
    browser.assert_called_once_with("https://gitcode.com/o/r/releases")
    assert run("view", "--web", "--json", "body").exit_code != 0
    assert run("list", "--json", "bad").exit_code != 0
    assert run("view", "-R", "github.com/o/r").exit_code != 0


def test_pagination_filtered(harness):
    run, c = harness
    c.get.side_effect = [[{**ROW, "prerelease": True}], [{**ROW, "tag_name": "stable"}]]
    assert "stable" in run("list", "-L", "1", "--exclude-pre-releases", "-O", "asc").output
    assert c.get.call_args_list[-1] == call(BASE, params={"direction": "asc", "page": 2, "per_page": 1})


def test_create_edit_payloads_and_no_implicit_writes(harness):
    run, c = harness
    tagged = {**ROW, "tag_name": "team/v1"}
    c.post.return_value = {**tagged, "name": "cut", "body": "hello", "release_status": "pre", "prerelease": True}
    c.get.return_value = [{"name": "team/v1"}]
    out = run(
        "create",
        "team/v1",
        "--verify-tag",
        "--target",
        "develop",
        "-t",
        "cut",
        "-F",
        "-",
        "--prerelease",
        stdin="hello",
    )
    assert out.exit_code == 0, out.exception
    c.post.assert_called_once_with(
        BASE,
        json={
            "name": "cut",
            "body": "hello",
            "tag_name": "team/v1",
            "target_commitish": "develop",
            "release_status": "pre",
        },
    )
    c.get.return_value = tagged
    c.patch.return_value = {**tagged, "body": ""}
    assert run("edit", "team/v1", "--notes", "").exit_code == 0
    c.patch.assert_called_once_with(BASE + "/team%2Fv1", json={"name": "Release", "body": ""})
    c.get.return_value = []
    assert run("create", "missing", "--verify-tag").exit_code != 0
    assert c.post.call_count == 1
    assert run("edit", "team/v1").exit_code != 0
    assert run("edit", "team/v1", "--latest", "--prerelease").exit_code != 0
    assert run("create", "team/v1", "-n", "notes", "-F", "-", stdin="xx").exit_code != 0
    c.get.return_value = {"tag_name": "team/v1"}
    assert run("edit", "team/v1", "--title", "new").exit_code != 0
    assert c.patch.call_count == 1


@posix_files
def test_upload_stream_and_verify(harness, tmp_path, monkeypatch):
    run, c = harness
    path = tmp_path / FILE["name"]
    path.write_bytes(DATA)
    c.get.side_effect = [{**ROW, "assets": []}, {"url": STORAGE, "headers": HEADER}, ROW]
    seen = []

    def put(req):
        seen.append(req)
        assert req.get_method() == "PUT" and req.full_url == STORAGE
        assert req.data.read(9999) == DATA
        assert req.get_header("Content-length") == str(len(DATA))
        assert not any(x in str(req.headers).lower() for x in ("authorization", "private-token", "access_token"))
        return Response(b"", 204)

    monkeypatch.setattr(binary, "_open", put)
    result = run("upload", "v1", str(path))
    assert result.exit_code == 0, result.exception
    assert len(seen) == 1
    assert c.get.call_args_list == [
        call(BASE + "/tags/v1"),
        call(BASE + "/v1/upload_url", params={"file_name": "build.zip"}),
        call(BASE + "/tags/v1"),
    ]
    c.get.side_effect = None
    c.get.return_value = ROW
    assert run("upload", "v1", str(path)).exit_code != 0
    assert len(seen) == 1


@posix_files
def test_create_reports_release_if_upload_unconfirmed(harness, tmp_path, monkeypatch):
    run, c = harness
    path = tmp_path / "test"
    path.write_bytes(DATA)
    c.post.return_value = {**ROW, "assets": [], "name": "v1", "body": ""}
    c.get.side_effect = [{"url": STORAGE, "headers": HEADER}, {**ROW, "assets": []}]
    monkeypatch.setattr(binary, "upload", lambda *_: (len(DATA), SHA))
    result = run("create", "v1", str(path))
    assert result.exit_code != 0 and "Published release v1" in result.output
    assert "registration" in str(result.exception)
    assert c.post.call_count == 1


def test_delete_by_id_only(harness):
    run, c = harness
    c.get.return_value = ROW
    assert run("delete-asset", "v1", "build.zip", stdin="n\n").exit_code != 0
    assert run("delete-asset", "v1", "missing", "-y").exit_code != 0
    assert run("delete-asset", "v1", "r-v1.zip", "-y").exit_code != 0
    c.delete.assert_not_called()
    c.get.side_effect = [ROW, {**ROW, "assets": [ARCH]}]
    assert run("delete-asset", "v1", "build.zip", "-y").exit_code == 0
    c.delete.assert_called_once_with(BASE + "/v1/attach_files/4")


@posix_files
def test_download_signed_bytes_atomic(harness, tmp_path, monkeypatch):
    run, c = harness
    tmp = {**ROW, "assets": [{**FILE, "temp_download_url": STORAGE}]}
    seen = []

    def get(req):
        seen.append(req)
        assert req.full_url == STORAGE
        assert sorted(req.header_items()) == [("Accept-encoding", "identity")]
        return Response(headers={"Content-Length": str(len(DATA))})

    monkeypatch.setattr(binary, "_open", get)
    c.get.side_effect = [ROW, tmp] * 4
    result = run("download", "-p", "*.zip", "-D", str(tmp_path))
    assert result.exit_code == 0, result.exception
    assert c.get.call_args_list[:2] == [
        call(BASE + "/latest", params={"type": "latest"}),
        call(BASE + "/v1", params={"temp_download_url": "true"}),
    ]
    path = tmp_path / "build.zip"
    assert path.read_bytes() == DATA and len(list(tmp_path.iterdir())) == 1
    assert run("download", "v1", "-D", str(tmp_path)).exit_code != 0
    assert run("download", "v1", "-D", str(tmp_path), "--skip-existing").exit_code == 0 and len(seen) == 1
    monkeypatch.setattr(binary, "_open", lambda _: Response(b"xxxx"))
    assert run("download", "v1", "-D", str(tmp_path), "--clobber").exit_code != 0
    assert path.read_bytes() == DATA and len(list(tmp_path.iterdir())) == 1


def test_archive_and_stdout(harness, monkeypatch):
    run, c = harness
    c.get.side_effect = [ROW, ROW]
    monkeypatch.setattr(binary, "_open", lambda _: Response(b"PK\n"))
    out = run("download", "v1", "--archive", "zip", "-O", "-")
    assert out.exit_code == 0 and out.stdout_bytes == b"PK\n"
    assert run("download").exit_code != 0
    assert run("download", "v1", "--clobber", "--skip-existing").exit_code != 0


@posix_files
def test_dangerous_metadata_prevents_fs_write(harness, tmp_path, monkeypatch):
    run, c = harness
    no_network = MagicMock(side_effect=AssertionError("unexpected HTTP"))
    monkeypatch.setattr(binary, "_open", no_network)
    c.get.side_effect = [ROW, {**ROW, "assets": [{**FILE, "id": 10000}]}]
    assert run("download", "v1", "-D", str(tmp_path)).exit_code != 0
    assert not list(tmp_path.iterdir())
    c.get.side_effect = [ROW, ROW]
    (tmp_path / "build.zip").symlink_to(tmp_path / "outside")
    assert run("download", "v1", "--clobber", "-D", str(tmp_path)).exit_code != 0
    assert not (tmp_path / "outside").exists()
    no_network.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "file:///a",
        "https://gitcode.com.evil.test/a",
        "https://foo@raw.gitcode.com/a",
        "http://gitcode.com/",
        "https://gitcode.com:444/a",
        "https://gitcode.com:bad/a",
        "https://gitcode.com/a?access_token=x",
        "https://gitcode.com/a#part",
        "https://gitcode.com/a\nx",
    ],
)
def test_bad_urls(url):
    with pytest.raises(GCError):
        binary.asset_url(url)


@pytest.mark.parametrize("name", ["../a", "a:b", "NUL.txt", "\\bad", ".git", "x\x1b[0m", "y."])
def test_bad_names(name):
    with pytest.raises(GCError):
        binary.asset_map({"assets": [{"name": name}]})


def test_redirection_checks_and_no_secrets(monkeypatch):
    signed = "never-render-this"

    def fail(req):
        headers = Message()
        headers["Location"] = "https://bad.invalid/x?Signature=" + signed
        raise HTTPError(req.full_url, 302, "redirect", headers, io.BytesIO())

    monkeypatch.setattr(binary, "_open", fail)
    with pytest.raises(GCError) as exc:
        binary.download(FILE, io.BytesIO())
    assert signed not in str(exc.value)
    assert binary._NoRedirect().redirect_request() is None


@pytest.mark.parametrize(
    ("meta", "response"),
    [
        ({"size": -1}, Response()),
        ({"digest": "md5:no"}, Response()),
        ({}, Response(status=206)),
        ({}, Response(headers={"Content-Encoding": "gzip"})),
        ({}, Response(headers={"Content-Length": "zzz"})),
        ({"size": 1}, Response()),
        ({"size": 10}, Response()),
        ({"digest": "0" * 64}, Response()),
    ],
)
def test_integrity_failures(meta, response, monkeypatch):
    monkeypatch.setattr(binary, "_open", lambda _: response)
    with pytest.raises(GCError):
        binary.download({"browser_download_url": RAW + "file", **meta}, io.BytesIO())


@pytest.mark.parametrize(
    "ticket",
    [
        {"url": STORAGE, "headers": {**HEADER, "Authorization": "danger"}},
        {"url": "https://example.test/x", "headers": HEADER},
        {"url": STORAGE, "headers": {**HEADER, "Content-Type": "x\r\ny"}},
    ],
)
def test_ticket_headers_not_forwarded(ticket, tmp_path):
    with pytest.raises(GCError):
        binary.upload(io.BytesIO(DATA), len(DATA), ticket)


def test_malformed_and_repeated_records_or_missing_tags():
    client = MagicMock()
    svc = ReleaseService(client, "owner", "repo")
    for row in ([], {}, {"tag_name": "wrong"}):
        with pytest.raises(APIError):
            release_record(row, "v")
    for tag in ("../v", "a//v", "", "v\\one"):
        with pytest.raises(APIError):
            tag_segment(tag)
    for result in ({}, [{"tag_name": ""}], [{"tag_name": "a"}, {"tag_name": "a"}]):
        client.get.return_value = result
        with pytest.raises(APIError):
            svc.list(3, "desc", False)
    client.get.return_value = [{"tag_name": "a"}]
    with pytest.raises(APIError, match="prerelease"):
        svc.list(1, "asc", True)
    client.get.return_value = {"tag_name": "latest"}
    assert svc.download_metadata("latest") == {"tag_name": "latest"}
    assert client.get.call_args == call("/repos/owner/repo/releases/tags/latest")
    client.get.side_effect = APIError("Signature=private", 403)
    for f in (lambda: svc.download_metadata("v1"), lambda: svc.ticket("v1", "file")):
        with pytest.raises(APIError, match="403") as exc:
            f()
        assert "Signature" not in str(exc.value)


def test_selection_uses_explicit_type_and_fails_closed():
    assert binary.is_archive({**FILE, "type": "SOURCE"})
    with pytest.raises(GCError):
        binary.is_archive({**FILE, "type": "EXTERNAL"})
    for value in ({}, {"assets": [None]}, {"assets": [FILE, {**FILE, "name": "BUILD.zip"}]}):
        with pytest.raises(GCError):
            binary.asset_map(value)
    with pytest.raises(GCError):
        binary.select_assets(ROW, ("*.nope",), None)
    with pytest.raises(GCError, match="metadata"):
        binary.check_registration(FILE, (len(DATA), "0" * 64))


@posix_files
def test_clobber_stop_after_unconfirmed_delete(harness, tmp_path, monkeypatch):
    run, c = harness
    file = tmp_path / "build.zip"
    file.write_bytes(DATA)
    c.get.side_effect = [ROW, ROW]
    spy = MagicMock()
    monkeypatch.setattr(binary, "upload", spy)
    result = run("upload", "v1", str(file), "--clobber")
    assert result.exit_code != 0 and "removal not confirmed" in str(result.exception)
    c.delete.assert_called_once_with(BASE + "/v1/attach_files/4")
    spy.assert_not_called()


@posix_files
def test_clobber_reports_partial_write_without_retry(harness, tmp_path, monkeypatch):
    run, c = harness
    file = tmp_path / "build.zip"
    file.write_bytes(DATA)
    c.get.side_effect = [ROW, {**ROW, "assets": []}, {"url": STORAGE, "headers": HEADER}]

    def fail(_):
        raise OSError("secret signature")

    monkeypatch.setattr(binary, "_open", fail)
    out = run("upload", "v1", str(file), "--clobber")
    assert "Deleted old asset build.zip" in out.output and out.exit_code != 0
    assert "signature" not in str(out.exception)
    assert c.delete.call_count == 1


def test_download_html_login_or_short_local_write(monkeypatch):
    monkeypatch.setattr(binary, "_open", lambda _: Response(headers={"Content-Type": "text/html; charset=UTF-8"}))
    with pytest.raises(GCError, match="web page"):
        binary.download(FILE, io.BytesIO())
    monkeypatch.setattr(binary, "_open", lambda _: Response())
    with pytest.raises(GCError, match="local release"):
        binary.download(FILE, MagicMock(write=lambda _: 0))


@posix_files
def test_no_reflected_token_in_signed_transfer(harness, tmp_path, monkeypatch):
    run, c = harness
    stream = MagicMock(side_effect=AssertionError("unexpected transfer"))
    monkeypatch.setattr(binary, "_open", stream)
    c.token = "offline+secret"
    c.get.side_effect = [ROW, {**ROW, "assets": [{**FILE, "temp_download_url": STORAGE + "&other=offline%2Bsecret"}]}]
    out = run("download", "v1", "-D", str(tmp_path))
    assert out.exit_code != 0 and "reflected" in str(out.exception)
    assert "offline" not in str(out.exception)
    c.get.side_effect = [
        {**ROW, "assets": []},
        {"url": STORAGE, "headers": {**HEADER, "x-obs-callback": "offline+secret"}},
    ]
    file = tmp_path / "test"
    file.write_bytes(DATA)
    assert run("upload", "v1", str(file)).exit_code != 0
    stream.assert_not_called()


def test_mutation_requires_verified_fields_and_does_not_repeat(harness):
    run, c = harness
    c.patch.return_value = ROW
    c.get.return_value = ROW
    out = run("edit", "v1", "--title", "new", "--prerelease")
    assert out.exit_code != 0
    assert "inspect remote state" in str(out.exception)
    assert "Updated release" not in out.output
    assert c.patch.call_count == 1
    assert c.get.call_count == 2

    c.post.return_value = {"tag_name": "v1"}
    c.get.return_value = {**ROW, "name": "new", "body": "test", "release_status": "lasted"}
    out = run("create", "v1", "--title", "new", "-n", "test", "--latest")
    assert out.exit_code == 0, out.exception
    assert "Published release" in out.output
    assert c.post.call_count == 1

    c.get.side_effect = APIError("private stuff", 502)
    out = run("create", "v1", "--title", "new")
    assert out.exit_code != 0 and "could not be verified" in str(out.exception)
    assert "private stuff" not in str(out.exception)
    assert "Published release" not in out.output
    assert c.post.call_count == 2


@posix_files
def test_unverified_create_never_uploads(harness, tmp_path):
    run, c = harness
    f = tmp_path / "file.bin"
    f.write_bytes(DATA)
    c.post.return_value = c.get.return_value = ROW
    out = run("create", "v1", str(f), "--title", "wrong")
    assert out.exit_code != 0
    assert c.post.call_count == 1
    c.get.assert_called_once_with(BASE + "/tags/v1")
    assert "Published release" not in out.output


@posix_files
def test_upload_inputs_reject_symlink_and_normalized_collisions(harness, tmp_path):
    run, c = harness
    target = tmp_path / "named"
    target.write_bytes(DATA)
    alias = tmp_path / "alias"
    alias.symlink_to(target)
    assert run("create", "v1", str(alias)).exit_code != 0
    child = tmp_path / "diralias"
    child.symlink_to(tmp_path, target_is_directory=True)
    assert run("upload", "v1", str(child / "named"), "--clobber").exit_code != 0
    c.get.assert_not_called()
    c.delete.assert_not_called()
    c.post.assert_not_called()
    sibling = tmp_path / "BuiLd.ZIP"
    sibling.write_bytes(DATA)
    c.get.return_value = ROW
    result = run("upload", "v1", str(sibling), "--clobber")
    assert result.exit_code != 0 and "normalization" in str(result.exception)
    c.delete.assert_not_called()
    first, second = tmp_path / "é.txt", tmp_path / "e\u0301.txt"
    first.write_bytes(DATA)
    second.write_bytes(DATA)
    result = run("upload", "v1", str(first), str(second))
    assert result.exit_code != 0 and "normalization" in str(result.exception)
    assert c.get.call_count == 1


@posix_files
def test_clobber_upload_uses_prewrite_snapshot(harness, tmp_path, monkeypatch):
    run, c = harness
    source = tmp_path / "build.zip"
    target = tmp_path / "secret.zip"
    source.write_bytes(DATA)
    target.write_bytes(b"must never be transferred")
    c.get.side_effect = [ROW, {**ROW, "assets": []}, {"url": STORAGE, "headers": HEADER}, ROW]

    def substitute(*_):
        source.write_bytes(b"this in-place rewrite should also not be transferred")
        source.unlink()
        source.symlink_to(target)

    c.delete.side_effect = substitute

    def put(req):
        assert req.data.read() == DATA
        return Response(status=204)

    monkeypatch.setattr(binary, "_open", put)
    out = run("upload", "v1", str(source), "--clobber")
    assert out.exit_code == 0, out.exception
    assert "Uploaded build.zip" in out.output


@posix_files
def test_download_fails_before_transfer_for_unsafe_ancestors_or_shared_parent(harness, tmp_path, monkeypatch):
    run, c = harness
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    blocked = MagicMock(side_effect=AssertionError("no network"))
    monkeypatch.setattr(binary, "_open", blocked)
    c.get.side_effect = [ROW, ROW] * 3
    assert run("download", "v1", "-D", str(link / "nested")).exit_code != 0
    outside.chmod(0o777)
    assert run("download", "v1", "-D", str(outside)).exit_code != 0
    assert run("download", "v1", "-D", str(outside / "new")).exit_code != 0
    assert not list(outside.iterdir())
    blocked.assert_not_called()


@posix_files
def test_parent_path_substitution_never_installs_download(harness, tmp_path, monkeypatch):
    run, c = harness
    intended = tmp_path / "dist"
    intended.mkdir()
    parked = tmp_path / "moved"
    redirected = tmp_path / "other"
    redirected.mkdir()
    c.get.side_effect = [ROW, ROW]

    def swap_parent(_):
        intended.rename(parked)
        intended.symlink_to(redirected, target_is_directory=True)
        return Response()

    monkeypatch.setattr(binary, "_open", swap_parent)
    result = run("download", "v1", "-D", str(intended), "--clobber")
    assert result.exit_code != 0
    assert not list(parked.iterdir())
    assert not list(redirected.iterdir())


@posix_files
def test_private_stage_substitution_never_installs_unverified_bytes(harness, tmp_path, monkeypatch):
    run, c = harness
    outside = tmp_path / "untouched"
    outside.write_bytes(b"outside")
    c.get.side_effect = [ROW, ROW]

    def substitute(_):
        stage = next(tmp_path.glob(".gc-release-*/payload"))
        stage.unlink()
        stage.symlink_to(outside)
        return Response()

    monkeypatch.setattr(binary, "_open", substitute)
    result = run("download", "v1", "-D", str(tmp_path), "--clobber")
    assert result.exit_code != 0 and "staging file changed" in str(result.exception)
    assert not list(tmp_path.glob(".gc-release-*"))
    assert not (tmp_path / "build.zip").exists()
    assert outside.read_bytes() == b"outside"


@posix_files
def test_create_safe_missing_parent_and_initialize_destination(harness, tmp_path, monkeypatch):
    run, c = harness
    destination = tmp_path / "outer" / "inner"
    c.get.side_effect = [ROW, ROW]
    monkeypatch.setattr(binary, "_open", lambda _: Response())
    result = run("download", "v1", "-D", str(destination))
    assert result.exit_code == 0, result.exception
    assert (destination / "build.zip").read_bytes() == DATA
    assert not list(destination.glob(".gc-release-*"))
    with pytest.raises(GCError, match="components"):
        with local.directory(tmp_path / ".."):
            pytest.fail("traversal was accepted")


def test_legacy_archive_example_is_not_classified_as_an_uploaded_file(harness):
    run, c = harness
    legacy = {
        **ARCH,
        "id": 1,
        "type": "zip",
        "browser_download_url": "https://api.atomgit.com/o/r/-/archive/v1/r-v1.zip",
    }
    assert binary.is_archive(legacy)
    c.get.return_value = [{**ROW, "assets": [legacy, FILE]}]
    out = run("list", "-L", "1", "--json", "assets")
    assert out.exit_code == 0, out.exception
    assert [row["name"] for row in json.loads(out.output)[0]["assets"]] == ["build.zip"]
    with pytest.raises(GCError):
        binary.is_archive(
            {**legacy, "browser_download_url": "https://api.atomgit.com/o/r/-/releases/v1/downloads/r-v1.zip"}
        )


@pytest.mark.parametrize(
    "path",
    [
        "/octocat/Hello-World/releases/download/v1.0.0/app.zip",
        "/octocat/Hello-World/-/releases/v1.0.0/downloads/app.zip",
    ],
)
def test_documented_mime_typed_attachment_requires_exact_route_and_positive_id(path):
    mime_attachment = {
        "name": "app.zip",
        "id": 42,
        "type": "application/zip",
        "browser_download_url": "https://api.atomgit.com" + path,
    }
    assert not binary.is_archive(mime_attachment)
    record = {**ROW, "assets": [ARCH, mime_attachment]}
    assert binary.select_assets(record, ("*.zip",), None) == [mime_attachment]
    assert binary.select_assets(record, (), "zip") == [ARCH]
    for override in (
        {"id": 0},
        {"id": None},
        {"id": True},
        {"id": "42"},
        {"browser_download_url": "https://api.atomgit.com/unrelated" + path},
        {"browser_download_url": "https://api.atomgit.com/o/r/releases/download/%2e%2e/app.zip"},
        {"browser_download_url": ARCH["browser_download_url"]},
        {"browser_download_url": "https://example.invalid" + path},
        {"type": "zip"},
        {"type": "application/zip; charset=UTF-8"},
    ):
        with pytest.raises(GCError):
            binary.is_archive({**mime_attachment, **override})


@pytest.mark.parametrize(
    "override",
    [
        {"id": None},
        {"id": True},
        {"id": 80},
        {"type": "SOURCE"},
    ],
)
def test_download_refuses_changed_temporary_identity_or_kind(harness, monkeypatch, override):
    run, c = harness
    c.get.side_effect = [ROW, {**ROW, "assets": [{**FILE, **override, "temp_download_url": STORAGE}]}]
    transfer = MagicMock(side_effect=AssertionError("download should not have started"))
    monkeypatch.setattr(binary, "_open", transfer)
    result = run("download", "v1", "-O", "-")
    assert result.exit_code != 0 and "Release assets changed" in str(result.exception)
    assert result.stdout_bytes == b""
    transfer.assert_not_called()


def test_download_mime_typed_attachment_accepts_stable_kind_and_id(harness, monkeypatch):
    run, c = harness
    asset = {**FILE, "type": "application/zip"}
    c.get.side_effect = [
        {**ROW, "assets": [ARCH, asset]},
        {**ROW, "assets": [{**asset, "type": "ATTACH_FILE", "temp_download_url": STORAGE}]},
    ]

    def get(req):
        assert req.full_url == STORAGE
        return Response()

    monkeypatch.setattr(binary, "_open", get)
    result = run("download", "v1", "-O", "-")
    assert result.exit_code == 0 and result.stdout_bytes == DATA


def test_signed_redirect_rejects_reflected_secret_before_transfer(harness, monkeypatch):
    run, c = harness
    c.token = "secret+pat"
    c.get.side_effect = [ROW, {**ROW, "assets": [{**FILE, "temp_download_url": STORAGE}]}]
    requests = []

    def redirect(req):
        requests.append(req.full_url)
        headers = Message()
        headers["Location"] = STORAGE + "&unrelated=secret%2Bpat"
        raise HTTPError(req.full_url, 302, "redirect", headers, io.BytesIO())

    monkeypatch.setattr(binary, "_open", redirect)
    result = run("download", "v1", "-O", "-")
    assert result.exit_code != 0 and "reflected API credentials" in str(result.exception)
    assert "secret+pat" not in str(result.exception)
    assert requests == [STORAGE]


def test_download_stdout_refuses_unknown_terminal_stream(harness, monkeypatch):
    run, c = harness
    c.get.side_effect = [ROW, ROW]
    monkeypatch.setattr(cmd.click, "get_binary_stream", lambda _: object())
    result = run("download", "v1", "-O", "-")
    assert result.exit_code != 0 and "terminal" in str(result.exception)
