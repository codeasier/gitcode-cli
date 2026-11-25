"""Read-only metadata/local byte comparison; no release attestations or asset download."""

import copy
import hashlib
import os
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

TAG = "v1.1"
NAME = "build.zip"
DATA = b"binary\x00\xff"
SHA = hashlib.sha256(DATA).hexdigest()
TOKEN = "contract-token-only"
ROW = {
    "type": "ATTACH_FILE",
    "name": NAME,
    "id": 16,
    "size": len(DATA),
    "digest": SHA,
    "browser_download_url": "https://storage.invalid/never-read?ticket=private",
}


@pytest.fixture
def invoke(monkeypatch, tmp_path):
    path = tmp_path / NAME
    path.write_bytes(DATA)
    calls = []
    klass = httpx.Client
    # Click 8.1 mixes stderr into stdout by default; newer versions separate them.
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))
    monkeypatch.setattr("gitcode_cli.cli.get_token", lambda: TOKEN)
    monkeypatch.setattr("gitcode_cli.repo_read.BASE_URL", "https://release.invalid/api/v5/")

    def run(*, rows=None, tag=TAG, args=None, body=None, status=200):
        def respond(request):
            calls.append(request)
            assert request.method == "GET"
            assert str(request.url) == f"https://release.invalid/api/v5/repos/owner/repo/releases/tags/{TAG}"
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert "private-token" not in request.headers and not request.content
            return httpx.Response(
                status, json={"tag_name": tag, "assets": rows if rows is not None else [ROW]} if body is None else body
            )

        def factory(**kwargs):
            assert kwargs == {"timeout": 30, "follow_redirects": False, "trust_env": False}
            return klass(transport=httpx.MockTransport(respond), **kwargs)

        monkeypatch.setattr("gitcode_cli.repo_read.httpx.Client", factory)
        result = runner.invoke(
            main, args if args is not None else ["release", "check-digest", TAG, str(path), "-R", "owner/repo"]
        )
        if result.exception and not isinstance(result.exception, SystemExit):
            raise result.exception
        for stream in (result.stdout, result.stderr):
            assert TOKEN not in stream and "ticket=" not in stream
        return result

    return run, calls, path


@pytest.mark.parametrize("digest", [SHA, "sha256:" + SHA.upper()])
def test_matches_without_downloading_or_clobbering(invoke, digest):
    run, calls, path = invoke
    before = path.stat()
    result = run(rows=[dict(ROW, digest=digest)])
    assert result.exit_code == 0 and "SHA-256 matches" in result.stdout and "not a publisher signature" in result.stdout
    assert len(calls) == 1 and before.st_mtime_ns == path.stat().st_mtime_ns and path.read_bytes() == DATA


@pytest.mark.parametrize(
    "patch",
    [
        {"digest": None},
        {"digest": "bad"},
        {"digest": "0" * 64},
        {"size": len(DATA) + 1},
        {"size": False},
        {"type": "SOURCE"},
        {"type": None},
        {"name": NAME.upper()},
        {"id": False},
    ],
)
def test_fail_without_positive_output(invoke, patch):
    run, calls, path = invoke
    result = run(rows=[dict(ROW, **patch)])
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1 and path.read_bytes() == DATA


@pytest.mark.parametrize("case", ["absent", "dupe", "tag", "denied", "missing-digest", "changed-bytes"])
def test_mismatch_is_not_a_pass(invoke, case):
    run, calls, path = invoke
    row = copy.deepcopy(ROW)
    if case == "missing-digest":
        del row["digest"]
    if case == "changed-bytes":
        path.write_bytes(b"x" * len(DATA))
    result = run(
        rows={"absent": [], "dupe": [row, dict(row, name=NAME.upper())]}.get(case, [row]),
        tag="other" if case == "tag" else TAG,
        status=403 if case == "denied" else 200,
    )
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1


@pytest.mark.parametrize("case", ["local-link", "fifo", "unsafe-mode", "oversize", "parent-link"])
def test_local_fail_closed(invoke, case, monkeypatch):
    run, calls, path = invoke
    if case == "local-link":
        target = path.with_suffix(".orig")
        path.rename(target)
        path.symlink_to(target)
    elif case == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif case == "unsafe-mode":
        path.chmod(0o666)
    elif case == "oversize":
        monkeypatch.setattr("gitcode_cli.release_files.MAX_CHECK_BYTES", 1)
    elif case == "parent-link":
        link = path.parent / "linked"
        link.symlink_to(path.parent, target_is_directory=True)
        path = link / path.name
    result = run(args=["release", "check-digest", TAG, str(path), "-R", "owner/repo"])
    assert result.exit_code != 0 and not result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["release", "check-digest", TAG, "build.zip"],
        ["release", "check-digest", TAG, "build.zip", "-R", "foreign.invalid/o/r"],
        ["-R", "other/repo", "release", "check-digest", TAG, "build.zip", "-R", "owner/repo"],
        ["release", "check-digest", "../bad", "build.zip", "-R", "owner/repo"],
        ["release", "verify-asset", TAG, "build.zip", "-R", "owner/repo"],
    ],
)
def test_reject_before_request(invoke, args):
    run, calls, _ = invoke
    result = run(args=args)
    assert result.exit_code != 0 and not calls


def test_no_gh_routing():
    with pytest.raises(ProxyError):
        validate_gitcode_command(["release", "check-digest", TAG, NAME, "-R", "gitcode.com/owner/repo"])


def test_one_id_cannot_identify_two_files(invoke):
    run, calls, _ = invoke
    result = run(rows=[ROW, dict(ROW, name="other.zip")])
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1


def test_metadata_size_optional_not_digest(invoke):
    run, calls, _ = invoke
    row = dict(ROW)
    del row["size"]
    result = run(rows=[row])
    assert result.exit_code == 0 and len(calls) == 1


@pytest.mark.parametrize("change", ["replace", "grow", "modify"])
def test_file_changed_during_hash_is_not_a_match(invoke, monkeypatch, change):
    run, calls, path = invoke
    original = hashlib.sha256

    class Hash:
        def __init__(self):
            self.inner = original()

        def update(self, block):
            self.inner.update(block)
            if change == "replace":
                replacement = path.with_suffix(".new")
                replacement.write_bytes(DATA)
                replacement.replace(path)
            elif change == "grow":
                with path.open("ab") as stream:
                    stream.write(b"x")
            else:
                path.write_bytes(b"x" * len(DATA))

        def hexdigest(self):
            return self.inner.hexdigest()

    monkeypatch.setattr("gitcode_cli.release_files.hashlib.sha256", Hash)
    result = run()
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1


def test_directory_input_fails_without_leaking_the_open_fd(invoke, monkeypatch):
    run, calls, path = invoke
    path.unlink()
    path.mkdir()
    opened = []
    raw_open = os.open

    def capture(*args, **kwargs):
        fd = raw_open(*args, **kwargs)
        if args[0] == NAME:
            opened.append(fd)
        return fd

    monkeypatch.setattr("gitcode_cli.release_files.os.open", capture)
    result = run()
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


ATTACH_ROUTE = f"https://gitcode.com/owner/repo/releases/download/{TAG}/{NAME}"


def test_live_attach_shape_matches_without_url_use(invoke, monkeypatch):
    run, calls, path = invoke

    def no_transfer(*args, **kwargs):
        pytest.fail("The attachment URL is identity metadata only")

    monkeypatch.setattr("gitcode_cli.release_assets._open", no_transfer)
    monkeypatch.setattr("gitcode_cli.commands.release.open_in_browser", no_transfer)
    before = path.stat()
    result = run(rows=[dict(ROW, type="attach", browser_download_url=ATTACH_ROUTE, digest="sha256:" + SHA)])
    assert result.exit_code == 0 and "SHA-256 matches" in result.stdout and not result.stderr
    assert len(calls) == 1
    assert before.st_mtime_ns == path.stat().st_mtime_ns and path.read_bytes() == DATA


@pytest.mark.parametrize(
    "fields",
    [
        {"browser_download_url": None},
        {"browser_download_url": ATTACH_ROUTE.replace("gitcode.com", "untrusted.invalid")},
        {"browser_download_url": ATTACH_ROUTE.replace("gitcode.com", "gitcode.com@untrusted.invalid")},
        {"browser_download_url": ATTACH_ROUTE.replace("gitcode.com", "userinfo@gitcode.com")},
        {"browser_download_url": ATTACH_ROUTE.replace("gitcode.com", "gitcode.com:444")},
        {"browser_download_url": ATTACH_ROUTE.replace("https://", "http://")},
        {"browser_download_url": ATTACH_ROUTE + "?ticket=private"},
        {"browser_download_url": ATTACH_ROUTE + "#anchor"},
        {"browser_download_url": ATTACH_ROUTE.replace("/owner/", "/other/")},
        {"browser_download_url": ATTACH_ROUTE.replace("/repo/", "/other/")},
        {"browser_download_url": ATTACH_ROUTE.replace(f"/{TAG}/", "/other/")},
        {"browser_download_url": ATTACH_ROUTE.replace(NAME, "other.zip")},
        {"browser_download_url": ATTACH_ROUTE.replace("/releases/download/", "/-/archive/")},
        {"browser_download_url": ATTACH_ROUTE.replace(f"/{TAG}/", f"/{TAG}/%2e%2e/{TAG}/")},
        {"browser_download_url": ATTACH_ROUTE.replace(f"/{TAG}/", f"/{TAG}%2F/")},
        {"browser_download_url": ATTACH_ROUTE.replace("/repo/releases/", "/repo%2Freleases/")},
        {"type": "source"},
        {"type": "ATTACH"},
        {"id": False},
        {"id": "16"},
        {"id": 0},
        {"digest": None},
        {"digest": "sha256:X" * 8},
        {"digest": "sha256:" + "0" * 64},
        {"size": len(DATA) + 1},
    ],
)
def test_live_attach_rejects_mismatched_identity_or_integrity(invoke, fields):
    run, calls, path = invoke
    row = {**ROW, "type": "attach", "browser_download_url": ATTACH_ROUTE, **fields}
    result = run(rows=[row])
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1
    assert result.stderr.startswith("error: ") and "https://" not in result.stderr
    assert path.read_bytes() == DATA


def test_live_attach_still_rejects_duplicate_id(invoke):
    run, calls, _ = invoke
    row = dict(ROW, type="attach", browser_download_url=ATTACH_ROUTE)
    result = run(rows=[row, dict(row, name="other.zip")])
    assert result.exit_code != 0 and not result.stdout and len(calls) == 1
    assert "Ambiguous release attachment ID" in result.stderr
