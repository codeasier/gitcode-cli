"""Offline GitCode v8 artifact contract and safety checks."""

from __future__ import annotations

import hashlib
import io
import json
import socket
import zipfile
from contextlib import nullcontext
from email.message import Message
from unittest.mock import MagicMock
from urllib.error import HTTPError

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import actions_artifact_zip as binary
from gitcode_cli.actions_client import ActionsClient
from gitcode_cli.commands import actions
from gitcode_cli.context import AppContext
from gitcode_cli.errors import APIError
from gitcode_cli.services.actions import ActionsService
from gitcode_cli.services.actions_artifacts import ActionsArtifactService

BASE = "/api/v8/repos/org/repo/actions"
COMMIT = "a" * 40
TOKEN = "synthetic-artifact-credential"
SIGNATURE = "synthetic-download-signature"
SIGNED = f"https://gitcode.com/signed-archive?Signature={SIGNATURE}"
RUN = {"workflow_run_id": "run-1", "workflow_id": "workflow-1", "head_sha": COMMIT, "attempt": 1}
FILE = io.BytesIO()
with zipfile.ZipFile(FILE, "w") as archive:
    archive.writestr("build.txt", b"fixture")
DATA = FILE.getvalue()
SHA = hashlib.sha256(DATA).hexdigest()
ARTIFACT = {
    "id": "artifact-77",
    "workflow_id": "workflow-1",
    "workflow_run_id": "run-1",
    "name": "build-package",
    "size_bytes": len(DATA),
    "digest": "sha256:" + SHA,
    "expires_at": "2999-01-01T00:00:00Z",
    "archive_download_url": SIGNED,
}


class Blob(io.BytesIO):
    def __init__(self, content=DATA, *, status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = Message()
        for key, val in headers or [("Content-Length", str(len(content)))]:
            self.headers[key] = val


@pytest.fixture
def harness(monkeypatch):
    api_requests = []
    response = {
        BASE + "/runs/run-1": lambda: httpx.Response(200, json=RUN),
        BASE + "/runs/run-1/artifacts": lambda: httpx.Response(200, json={"total_count": 1, "artifacts": [ARTIFACT]}),
        BASE + "/artifacts/artifact-77": lambda: httpx.Response(200, json={**ARTIFACT, "digest": SHA.upper()}),
        BASE + "/artifacts/artifact-77/zip": lambda: httpx.Response(302, headers={"Location": SIGNED}),
    }

    def api(req):
        api_requests.append(req)
        assert req.method == "GET"
        assert req.url.scheme == "https" and req.url.host == "api.gitcode.com"
        assert req.url.params["access_token"] == TOKEN
        assert not {"authorization", "cookie", "private-token"} & set(req.headers)
        return response[req.url.path]()

    client = ActionsClient(TOKEN, transport=httpx.MockTransport(api))
    svc = ActionsService(client, "org", "repo")
    monkeypatch.setattr(actions, "_service", lambda *_: nullcontext(svc))

    def invoke(*arguments):
        return CliRunner().invoke(actions.run, arguments, obj={"app": AppContext(TOKEN, "org/repo")})

    try:
        yield invoke, api_requests, response
    finally:
        client.close()


def test_list_artifact_attempt_visibility_and_no_urls(harness):
    invoke, requests, response = harness
    res = invoke("artifacts", "run-1", "--limit", "1")
    assert res.exit_code == 0, res.exception
    value = json.loads(res.output)
    assert value["artifact_attempt"] == 1
    assert value["artifacts"][0]["id"] == "artifact-77"
    assert "url" not in res.output and SIGNATURE not in res.output
    assert requests[1].url.path == BASE + "/runs/run-1/artifacts"
    assert dict(requests[1].url.params) == {
        "access_token": TOKEN,
        "page": "1",
        "per_page": "1",
        "sort": "created",
        "direction": "asc",
    }

    response[BASE + "/runs/run-1"] = lambda: httpx.Response(200, json={**RUN, "attempt": 2})
    res = invoke("artifacts", "run-1", "-a", "2")
    assert res.exit_code == 0
    assert json.loads(res.output)["artifact_attempt"] is None


def fetch(invoke, output, *args):
    return invoke(
        "download", "run-1", "--artifact-id", "artifact-77", "-a", "1", "--commit", COMMIT, "-O", str(output), *args
    )


def test_download_has_no_redirect_credentials_or_extract(harness, tmp_path, monkeypatch, caplog):
    invoke, requests, _ = harness
    records = []

    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 30
            records.append(request)
            return Blob()

    monkeypatch.setattr(binary, "build_opener", lambda *_: Opener())
    target = tmp_path / "file.zip"
    with caplog.at_level("INFO", logger="httpx"):
        result = fetch(invoke, target)
    assert result.exit_code == 0, result.exception
    assert json.loads(result.output)["sha256"] == SHA
    assert SIGNATURE not in result.output and TOKEN not in caplog.text and SIGNATURE not in caplog.text
    assert target.read_bytes() == DATA
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.zip"]
    assert records[0].full_url == SIGNED
    assert dict(records[0].header_items()) == {"Accept": "application/zip", "Accept-encoding": "identity"}
    assert [r.url.path[len(BASE) :] for r in requests] == [
        "/runs/run-1",
        "/runs/run-1/artifacts",
        "/artifacts/artifact-77",
        "/runs/run-1",
        "/artifacts/artifact-77/zip",
        "/artifacts/artifact-77",
        "/runs/run-1",
    ]


@pytest.mark.parametrize(
    "changed",
    [
        {"workflow_id": "wrong"},
        {"workflow_run_id": "wrong"},
        {"id": "different"},
        {"digest": "1" * 64},
        {"size_bytes": binary.MAX_ZIP_BYTES + 1},
        {"expires_at": "1"},
    ],
)
def test_malformed_artifact_detail_prevents_download(harness, tmp_path, monkeypatch, changed):
    invoke, requests, response = harness
    detail = BASE + "/artifacts/artifact-77"
    response[detail] = lambda: httpx.Response(200, json={**ARTIFACT, **changed})
    call = MagicMock()
    monkeypatch.setattr(binary, "_open", call)
    result = fetch(invoke, tmp_path / "file.zip")
    assert result.exit_code != 0
    assert not tuple(tmp_path.iterdir())
    assert all(not req.url.path.endswith("/zip") for req in requests)
    call.assert_not_called()


@pytest.mark.parametrize(
    "location",
    [
        "http://gitcode.com/zip",
        "https://gitcode.com:444/a",
        "https://gitcode.com@else.invalid/a",
        "https://gitcode.com.evil.invalid/a",
        "https://storage.example.invalid/a",
        "https://gitcode.com/a?%61ccess_token=dont-echo",
        f"https://gitcode.com/a?q={TOKEN}",
    ],
)
def test_unapproved_target_fails_without_request(harness, tmp_path, monkeypatch, location):
    invoke, _, response = harness
    response[BASE + "/artifacts/artifact-77/zip"] = lambda: httpx.Response(302, headers={"Location": location})
    open_blob = MagicMock()
    monkeypatch.setattr(binary, "_open", open_blob)
    result = fetch(invoke, tmp_path / "file.zip")
    assert result.exit_code != 0 and "untrusted" in str(result.exception)
    assert "dont-echo" not in result.output and TOKEN not in result.output
    assert not tuple(tmp_path.iterdir())
    open_blob.assert_not_called()


def test_follow_only_validated_hops(monkeypatch):
    opened = []

    def opener(url):
        opened.append(url)
        if len(opened) == 1:
            headers = Message()
            headers["Location"] = "/next-location?Signature=not-for-output"
            raise HTTPError(url, 302, "redirect", headers, io.BytesIO())
        return Blob()

    monkeypatch.setattr(binary, "_open", opener)
    stage = io.BytesIO()
    binary.stream_zip("https://api.gitcode.com", SIGNED, stage, len(DATA), SHA, token=TOKEN)
    assert stage.getvalue() == DATA
    assert opened == [SIGNED, "https://gitcode.com/next-location?Signature=not-for-output"]


@pytest.mark.parametrize(
    "blob",
    [
        Blob(status=206),
        Blob(headers=[("Content-Encoding", "gzip")]),
        Blob(headers=[("Content-Length", str(len(DATA))), ("Content-Length", str(len(DATA)))]),
        Blob(DATA[:-1]),
        Blob(b"x" * len(DATA)),
        Blob(DATA + b"extra", headers=[("X-Example-Header", "yes")]),
    ],
)
def test_corrupt_or_incomplete_transfer_never_installs(harness, tmp_path, monkeypatch, blob):
    invoke, _, _ = harness
    monkeypatch.setattr(binary, "_open", lambda _: blob)
    assert fetch(invoke, tmp_path / "file.zip").exit_code != 0
    assert not tuple(tmp_path.iterdir())


def test_hash_valid_but_not_zip(monkeypatch):
    content = b"a" * len(DATA)
    monkeypatch.setattr(binary, "_open", lambda _: Blob(content))
    with pytest.raises(APIError, match="not a ZIP"):
        binary.stream_zip(SIGNED, SIGNED, io.BytesIO(), len(content), hashlib.sha256(content).hexdigest(), token=TOKEN)


def test_attempt_and_existing_output_guards(harness, tmp_path):
    invoke, requests, _ = harness
    target = tmp_path / "file.zip"
    assert fetch(invoke, target, "-a", "2").exit_code != 0
    target.write_bytes(b"previous")
    assert fetch(invoke, target).exit_code != 0
    assert target.read_bytes() == b"previous"
    assert not requests


def test_no_install_on_attempt_change_during_transfer(harness, tmp_path, monkeypatch):
    invoke, _, response = harness

    def download(_):
        response[BASE + "/runs/run-1"] = lambda: httpx.Response(200, json={**RUN, "attempt": 2})
        return Blob()

    monkeypatch.setattr(binary, "_open", download)
    result = fetch(invoke, tmp_path / "file.zip")
    assert result.exit_code != 0 and "no longer matches" in str(result.exception)
    assert not tuple(tmp_path.iterdir())


def test_output_race_never_overwrites(harness, tmp_path, monkeypatch):
    invoke, _, _ = harness
    target = tmp_path / "file.zip"

    def download(_):
        target.write_bytes(b"other writer")
        return Blob()

    monkeypatch.setattr(binary, "_open", download)
    assert fetch(invoke, target).exit_code != 0
    assert target.read_bytes() == b"other writer"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.zip"]


def test_output_symlink_and_shared_directory_refused(harness, tmp_path):
    invoke, requests, _ = harness
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert fetch(invoke, alias / "file.zip").exit_code != 0
    real.chmod(0o777)
    assert fetch(invoke, real / "file.zip").exit_code != 0
    assert not requests and not tuple(real.iterdir())


def test_private_or_non_public_dns_fails_before_opening_socket(monkeypatch):
    opened = MagicMock()
    monkeypatch.setattr(binary.socket, "socket", opened)
    for target in ("127.0.0.1", "10.1.2.3", "::ffff:127.0.0.1", "169.254.169.254", "224.1.2.3"):
        monkeypatch.setattr(
            binary.socket,
            "getaddrinfo",
            lambda *_args, target=target, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (target, 443))],
        )
        with pytest.raises(OSError):
            binary._connect_public(("gitcode.com", 443))
    opened.assert_not_called()


def test_validated_ip_is_used_without_second_dns(monkeypatch):
    opened = MagicMock()
    resolve = MagicMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 443))])
    monkeypatch.setattr(binary.socket, "socket", opened)
    monkeypatch.setattr(binary.socket, "getaddrinfo", resolve)
    result = binary._connect_public(("gitcode.com", 443))
    resolve.assert_called_once_with("gitcode.com", 443, type=socket.SOCK_STREAM)
    result.connect.assert_called_once_with(("1.1.1.1", 443))


def test_bounded_pages_never_mix_artifacts(monkeypatch):
    client = MagicMock()
    svc = ActionsArtifactService(ActionsService(client, "org", "repo"))
    monkeypatch.setattr("gitcode_cli.services.actions_artifacts.MAX_PAGE", 1)
    page = {"total_count": 2, "artifacts": [ARTIFACT]}
    client.call.side_effect = [page, page]
    with pytest.raises(APIError, match="overlapping"):
        svc._find(RUN, ARTIFACT["id"])
