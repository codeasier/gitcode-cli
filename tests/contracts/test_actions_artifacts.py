"""Offline GitCode v8 artifact contract and safety checks."""

from __future__ import annotations

import hashlib
import io
import json
import os
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
    "created_at": None,
    "updated_at": None,
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
    # The list contract returns all three timestamp keys; neither optional
    # timestamp is assumed to exist in the separately read detail response.
    detail = {key: value for key, value in ARTIFACT.items() if key not in {"created_at", "updated_at"}}
    response = {
        BASE + "/runs/run-1": lambda: httpx.Response(200, json=RUN),
        BASE + "/runs/run-1/artifacts": lambda: httpx.Response(200, json={"total_count": 1, "artifacts": [ARTIFACT]}),
        BASE + "/artifacts/artifact-77": lambda: httpx.Response(200, json={**detail, "digest": SHA.upper()}),
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


def name_fetch(invoke, output, *selectors):
    return invoke("download", "run-1", "-a", "1", "--commit", COMMIT, "-O", str(output), *selectors)


def artifact_pages(harness, monkeypatch, *pages):
    _, _, routes = harness
    monkeypatch.setattr("gitcode_cli.services.actions_artifacts.MAX_PAGE", 1)
    responses = iter(pages)
    routes[BASE + "/runs/run-1/artifacts"] = lambda: httpx.Response(200, json=next(responses))


def page(row, total):
    return {"artifacts": [row], "total_count": total}


OTHER = {**ARTIFACT, "id": "artifact-88", "name": ARTIFACT["name"] + "-debug"}


def test_exact_name_on_second_page_resolves_to_one_pinned_id(harness, monkeypatch, tmp_path):
    invoke, requests, _ = harness
    # Equal creation timestamps may reorder unrelated rows in the second observation.
    other = {**OTHER, "size_bytes": binary.MAX_ZIP_BYTES + 1, "expires_at": None}
    a, b = page(ARTIFACT, 2), page(other, 2)
    artifact_pages(harness, monkeypatch, b, a, a, b)
    monkeypatch.setattr(binary, "_open", lambda _: Blob())
    output = tmp_path / "selected.zip"
    result = name_fetch(invoke, output, "--name", ARTIFACT["name"])
    assert result.exit_code == 0, result.exception
    data = json.loads(result.output)
    assert data["artifact_id"] == ARTIFACT["id"] and data["artifact_attempt"] == 1 and data["sha256"] == SHA
    assert output.read_bytes() == DATA
    list_requests = [r for r in requests if r.url.path.endswith("/artifacts")]
    assert [r.url.params["page"] for r in list_requests] == ["1", "2", "1", "2"]
    assert all("name" not in r.url.params for r in requests)
    assert [r.url.path for r in requests if r.url.path.endswith("/zip")] == [BASE + "/artifacts/artifact-77/zip"]


@pytest.mark.parametrize(
    "selectors",
    [
        (),
        ("--name", ""),
        ("--name", " "),
        ("--name", "no\ncontrol"),
        ("--name", "x" * 1025),
        ("--name", "a", "--name", "b"),
        ("--artifact-id", "a", "--name", "b"),
        ("--artifact-id", "a", "--artifact-id", "b"),
    ],
)
def test_accept_only_one_explicit_selector(harness, tmp_path, selectors):
    invoke, requests, _ = harness
    assert name_fetch(invoke, tmp_path / "file.zip", *selectors).exit_code != 0
    assert not requests and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["BUILD-PACKAGE", "build", "build-*", ARTIFACT["id"]])
def test_names_do_not_fallback_to_fuzzy_glob_or_id(harness, tmp_path, name):
    invoke, requests, _ = harness
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", name)
    assert result.exit_code != 0 and "not present" in str(result.exception)
    assert len(requests) == 2 and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("pages", "error"),
    [
        ([page(ARTIFACT, 2), page({**OTHER, "name": ARTIFACT["name"]}, 2)], "More than one"),
        ([page(ARTIFACT, 2), page(ARTIFACT, 2)], "overlapping"),
        ([page(ARTIFACT, 2), page(OTHER, 3)], "list changed"),
        ([page(ARTIFACT, 21)], "bounded scan"),
        ([page(ARTIFACT, 2), {"artifacts": [], "total_count": 2}], "incomplete"),
        ([page(ARTIFACT, 2), page({**OTHER, "workflow_run_id": "other-run"}, 2)], "identity"),
        ([page(ARTIFACT, 2), page({**OTHER, "workflow_id": "other-workflow"}, 2)], "identity"),
        ([page(ARTIFACT, 2), page({**OTHER, "name": None}, 2)], "identity"),
        ([page(ARTIFACT, 2), page({**OTHER, "digest": {"sha256": SHA}}, 2)], "Invalid Actions artifact metadata"),
        ([page(ARTIFACT, 2), page({**OTHER, "size_bytes": True}, 2)], "Invalid Actions artifact metadata"),
    ],
)
def test_scan_rejects_unprovable_selection_even_after_early_match(harness, monkeypatch, tmp_path, pages, error):
    invoke, requests, _ = harness
    artifact_pages(harness, monkeypatch, *pages)
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", ARTIFACT["name"])
    assert result.exit_code != 0 and error in str(result.exception)
    assert all("/artifacts/" not in req.url.path for req in requests) and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize(
    "after",
    [
        [page(OTHER, 1)],  # removed
        [page({**ARTIFACT, "id": "new-id"}, 1)],  # replaced with the same name
        [page({**ARTIFACT, "digest": "3" * 64}, 1)],  # same ID, changed metadata
        [page(ARTIFACT, 2), page(OTHER, 2)],  # added unrelated artifact
        [page(ARTIFACT, 2), page({**OTHER, "name": ARTIFACT["name"]}, 2)],  # now ambiguous
    ],
)
def test_recheck_the_complete_listing_before_install(harness, monkeypatch, tmp_path, after):
    invoke, requests, _ = harness
    artifact_pages(harness, monkeypatch, page(ARTIFACT, 1), *after)
    monkeypatch.setattr(binary, "_open", lambda _: Blob())
    output = tmp_path / "selected.zip"
    result = name_fetch(invoke, output, "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError)
    assert sum(r.url.path.endswith("/zip") for r in requests) == 1
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("change", [{"attempt": 2}, {"attempt": None}, {"head_sha": "f" * 40}, {"workflow_id": "wf-2"}])
def test_name_lookup_keeps_attempt_sha_and_workflow_pinned(harness, monkeypatch, tmp_path, change):
    invoke, _, routes = harness

    def during_transfer(_):
        routes[BASE + "/runs/run-1"] = lambda: httpx.Response(200, json={**RUN, **change})
        return Blob()

    monkeypatch.setattr(binary, "_open", during_transfer)
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size_bytes", "122"),
        ("size_bytes", -1),
        ("digest", None),
        ("digest", []),
        ("expires_at", {"iso": "2999-01-01T00:00:00Z"}),
        ("expires_at", 9999999999999),
        ("created_at", ["2999-01-01T00:00:00Z"]),
        ("updated_at", True),
    ],
)
def test_artifact_list_rejects_bad_public_field_types(harness, field, value):
    invoke, _, routes = harness
    row = {**ARTIFACT, field: value}
    routes[BASE + "/runs/run-1/artifacts"] = lambda: httpx.Response(200, json=page(row, 1))
    result = invoke("artifacts", "run-1")
    assert isinstance(result.exception, APIError) and "Invalid Actions artifact metadata" in str(result.exception)


@pytest.mark.parametrize("source", ["list", "detail"])
def test_malformed_expiry_is_not_dropped_and_treated_as_unlimited(harness, tmp_path, source):
    invoke, requests, routes = harness
    row = {**ARTIFACT, "expires_at": {"iso": "2999-01-01T00:00:00Z"}}
    if source == "list":
        routes[BASE + "/runs/run-1/artifacts"] = lambda: httpx.Response(200, json=page(row, 1))
    else:
        routes[BASE + "/artifacts/artifact-77"] = lambda: httpx.Response(200, json=row)
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "Invalid Actions artifact metadata" in str(result.exception)
    assert not any(req.url.path.endswith("/zip") for req in requests) and not tuple(tmp_path.iterdir())


def watch_stage_open(monkeypatch):
    calls = []
    original = os.open

    def track_open(path, flags, *args, **kwargs):
        if str(path).startswith(".gc-artifact-"):
            calls.append((path, flags))
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(binary.os, "open", track_open)
    return calls


@pytest.mark.parametrize("selector", ["--name", "--artifact-id"])
def test_preflight_has_no_entries_until_run_list_detail_and_repin_match(harness, monkeypatch, tmp_path, selector):
    invoke, requests, routes = harness
    stage_opens = watch_stage_open(monkeypatch)
    checked = []

    def read_remote_metadata():
        checked.append(requests[-1].url.path[len(BASE) :])
        if len(checked) <= 4:
            assert not stage_opens and not tuple(tmp_path.iterdir())

    def check_route(callback):
        def read():
            read_remote_metadata()
            return callback()

        return read

    for route, callback in list(routes.items()):
        if not route.endswith("/zip"):
            routes[route] = check_route(callback)

    def open_storage(_):
        staged = list(tmp_path.iterdir())
        assert len(stage_opens) == len(staged) == 1
        assert staged[0].name.startswith(".gc-artifact-") and staged[0].stat().st_size == 0
        assert staged[0].stat().st_mode & 0o077 == 0
        return Blob()

    monkeypatch.setattr(binary, "_open", open_storage)
    output = tmp_path / "selected.zip"
    key = "name" if selector == "--name" else "id"
    result = name_fetch(invoke, output, selector, ARTIFACT[key])
    assert result.exit_code == 0, result.exception
    assert checked[:4] == ["/runs/run-1", "/runs/run-1/artifacts", "/artifacts/artifact-77", "/runs/run-1"]
    assert output.read_bytes() == DATA and tuple(tmp_path.iterdir()) == (output,)


@pytest.mark.parametrize("phase", ["run", "listing", "detail", "repin"])
def test_failed_initial_metadata_check_creates_no_temp_entry(harness, monkeypatch, tmp_path, phase):
    invoke, requests, routes = harness
    stage_opens = watch_stage_open(monkeypatch)
    target = tmp_path / "selected.zip"
    run_key = BASE + "/runs/run-1"
    if phase in {"run", "repin"}:
        initial_run = routes[run_key]
        routes[run_key] = lambda: (
            initial_run()
            if phase == "repin" and len(requests) == 1
            else httpx.Response(200, json={**RUN, "attempt": 2})
        )
    elif phase == "listing":
        routes[run_key + "/artifacts"] = lambda: httpx.Response(200, json={"artifacts": [], "total_count": 1})
    else:
        routes[BASE + "/artifacts/artifact-77"] = lambda: httpx.Response(200, json={**ARTIFACT, "digest": "x"})
    result = name_fetch(invoke, target, "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError)
    assert not stage_opens and not any(req.url.path.endswith("/zip") for req in requests)
    assert not tuple(tmp_path.iterdir())


def test_existing_output_created_during_prevalidation_is_refused_before_staging(harness, monkeypatch, tmp_path):
    invoke, requests, routes = harness
    stage_opens = watch_stage_open(monkeypatch)
    target = tmp_path / "selected.zip"
    victim = tmp_path / "unrelated"
    victim.write_bytes(b"do not modify")
    detail = BASE + "/artifacts/artifact-77"
    initial_detail = routes[detail]

    def create_output_link():
        target.symlink_to(victim)
        return initial_detail()

    routes[detail] = create_output_link
    result = name_fetch(invoke, target, "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "already exists" in str(result.exception)
    assert not stage_opens and not any(req.url.path.endswith("/zip") for req in requests)
    assert target.is_symlink() and target.readlink() == victim and victim.read_bytes() == b"do not modify"


def test_permissions_changed_during_prevalidation_are_rechecked(harness, monkeypatch, tmp_path):
    invoke, requests, routes = harness
    stage_opens = watch_stage_open(monkeypatch)
    detail = BASE + "/artifacts/artifact-77"
    initial_detail = routes[detail]

    def directory_permissions_changed():
        tmp_path.chmod(0o777)
        return initial_detail()

    routes[detail] = directory_permissions_changed
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "not writable" in str(result.exception)
    assert not stage_opens and not any(req.url.path.endswith("/zip") for req in requests)
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("field", ["expires_at", "created_at", "updated_at"])
def test_list_requires_each_nullable_field_even_on_unselected_row(harness, monkeypatch, tmp_path, field):
    invoke, requests, _ = harness
    stage_opens = watch_stage_open(monkeypatch)
    incomplete = {key: value for key, value in OTHER.items() if key != field}
    artifact_pages(harness, monkeypatch, page(ARTIFACT, 2), page(incomplete, 2))
    result = name_fetch(invoke, tmp_path / "selected.zip", "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "Invalid Actions artifact metadata" in str(result.exception)
    assert not stage_opens and not any("/artifacts/" in req.url.path for req in requests)
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("phase", ["prevalidation", "transfer"])
@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_path_replaced_after_preflight_cannot_report_success(harness, monkeypatch, tmp_path, phase, replacement):
    invoke, requests, routes = harness
    stage_opens = watch_stage_open(monkeypatch)
    requested = tmp_path / "requested"
    requested.mkdir()
    moved = tmp_path / "moved"
    target = requested / "selected.zip"

    def replace_path():
        requested.rename(moved)
        if replacement == "directory":
            requested.mkdir()
        else:
            alias_target = tmp_path / "other"
            alias_target.mkdir()
            requested.symlink_to(alias_target, target_is_directory=True)
        target.write_bytes(b"another owner's output")

    if phase == "prevalidation":
        detail = BASE + "/artifacts/artifact-77"
        initial_detail = routes[detail]

        def read_detail():
            replace_path()
            return initial_detail()

        routes[detail] = read_detail

    def read_storage(_):
        assert phase == "transfer"
        replace_path()
        return Blob()

    monkeypatch.setattr(binary, "_open", read_storage)
    result = name_fetch(invoke, target, "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "output directory changed" in str(result.exception)
    assert sum(req.url.path.endswith("/zip") for req in requests) == len(stage_opens) == (phase == "transfer")
    assert not result.output and not tuple(moved.iterdir())
    assert target.read_bytes() == b"another owner's output"


def test_change_during_atomic_link_is_reported_without_deleting_any_final_path(harness, monkeypatch, tmp_path):
    invoke, _, _ = harness
    requested = tmp_path / "requested"
    requested.mkdir()
    target = requested / "selected.zip"
    moved = tmp_path / "moved"
    link = os.link

    def replace_path_after_link(source, destination, **kwargs):
        link(source, destination, **kwargs)
        assert destination == target.name
        requested.rename(moved)
        requested.mkdir()
        target.write_bytes(b"another owner's output")

    monkeypatch.setattr(binary.os, "link", replace_path_after_link)
    monkeypatch.setattr(binary, "_open", lambda _: Blob())
    result = name_fetch(invoke, target, "--name", ARTIFACT["name"])
    assert isinstance(result.exception, APIError) and "may remain in the original directory" in str(result.exception)
    assert not result.output and target.read_bytes() == b"another owner's output"
    assert sorted(p.name for p in moved.iterdir()) == [target.name]
    assert (moved / target.name).read_bytes() == DATA
