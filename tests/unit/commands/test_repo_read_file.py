"""Exercise CLI, identity checks, strict transport and stdout without a live provider."""

from __future__ import annotations

import base64
import errno
import hashlib
import inspect
import json
import os
from unittest.mock import Mock

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import repo_read as reads
from gitcode_cli import repo_read_file as files
from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

ARGS = ["repo", "read-file", "-R", "gitcode.com/team/project"]


def _runner():
    if "mix_stderr" in inspect.signature(CliRunner.__init__).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


def record(path, data):
    return {
        "type": "file",
        "encoding": "base64",
        "size": len(data),
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "content": base64.b64encode(data).decode(),
        "sha": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(),
        "download_url": "https://elsewhere.invalid/ignored",
    }


@pytest.fixture
def provider(monkeypatch, tmp_config_dir):
    real = httpx.Client
    monkeypatch.delenv("GC_TOKEN", raising=False)

    def configure(handler):
        fake = Mock(side_effect=handler)
        monkeypatch.setattr(reads.httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(fake), **kwargs))
        return fake

    return configure


@pytest.mark.parametrize("data", ["你好\r\n\tbye".encode(), b""])
def test_exact_single_contents_read(data, provider):
    path = "dir/文 %2F?#.txt"

    def handle(req):
        assert req.method == "GET"
        assert req.url.host == "api.gitcode.com"
        assert req.url.raw_path.split(b"?")[0] == b"/api/v5/repos/team/project/contents/dir/%E6%96%87%20%252F%3F%23.txt"
        assert dict(req.url.params) == {"ref": "topic/feature#1"}
        assert req.headers["Authorization"] == "Bearer synthetic"
        assert "private-token" not in req.headers
        return httpx.Response(200, json=record(path, data))

    requests = provider(handle)
    res = _runner().invoke(main, ["--token", "synthetic", *ARGS, "--ref", "topic/feature#1", path])
    assert res.exit_code == 0, res.output
    assert res.stdout_bytes == data
    requests.assert_called_once()


@pytest.mark.parametrize(
    "origin", ["https://gitcode.com/team/dotted.project.git", "git@ssh.gitcode.com:team/dotted.project.git"]
)
def test_default_ref_inferred_from_exact_origin(origin, monkeypatch, provider):
    monkeypatch.setattr("gitcode_cli.commands.repo._origin_repository_arg", lambda: origin)

    def handle(req):
        assert req.url.path == "/api/v5/repos/team/dotted.project/contents/README"
        assert "ref" not in req.url.params
        assert "authorization" not in req.headers
        return httpx.Response(200, json=record("README", b"test"))

    provider(handle)
    res = _runner().invoke(main, ["repo", "read-file", "README"])
    assert res.exit_code == 0
    assert res.stdout_bytes == b"test"


@pytest.mark.parametrize(
    "origin",
    [
        "https://gitcode.com:8443/team/proj",
        "https://test-secret@github.com/team/proj",
        "https://gitcode.com/not/team/proj",
    ],
)
def test_refuse_ambiguous_origin(origin, monkeypatch, provider):
    monkeypatch.setattr("gitcode_cli.commands.repo._origin_repository_arg", lambda: origin)
    req = provider(lambda _: pytest.fail("must not contact provider"))
    res = _runner().invoke(main, ["repo", "read-file", "f"])
    assert res.exit_code != 0 and "test-secret" not in res.stderr
    req.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["-R", "tenant.gitcode.com/o/r", "f"],
        ["-R", "o/%72", "f"],
        ["-R", "", "f"],
        ["-R", "o/r", "../x"],
        ["-R", "o/r", "a//b"],
        ["-R", "o/r", "C:/Windows"],
        ["-R", "o/r", ""],
        ["-R", "o/r", "/abs"],
        ["-R", "o/r", "https://other.invalid/x"],
        ["-R", "o/r", "f\nX"],
        ["-R", "o/r", "f", "--ref", ""],
        ["-R", "o/r", "f", "--ref", "bad..ref"],
        ["-R", "o/r", "f", "--ref", "refs/*"],
        ["-R", "o/r", "f", "--ref", "@"],
    ],
)
def test_invalid_input_never_sends(args, provider):
    req = provider(lambda _: pytest.fail("unexpected request"))
    assert _runner().invoke(main, ["repo", "read-file", *args]).exit_code != 0
    req.assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"type": "dir"},
        {"path": "elsewhere"},
        {"name": "wrong"},
        {"encoding": "none"},
        {"size": True},
        {"size": -1},
        {"size": files.MAX_FILE + 1},
        {"content": None},
        {"content": ""},
        {"content": "!!!!"},
        {"content": "Yh=="},
        {"size": 2},
        {"sha": "0" * 40},
        {"encoding": "base64", "content": "，。。。"},
    ],
)
def test_bad_blob_never_creates_output(updates, provider, tmp_path):
    dest = tmp_path / "should-not-exist"
    req = provider(lambda _: httpx.Response(200, json={**record("f", b"a"), **updates}))
    res = _runner().invoke(main, [*ARGS, "f", "--output", str(dest)])
    assert res.exit_code == 1 and not res.stdout_bytes and not dest.exists()
    req.assert_called_once()


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, json=[]),
        httpx.Response(200, content=b"not JSON"),
        httpx.Response(200, content=b'{"type":"dir","type":"file"}'),
        httpx.Response(200, content=b" " * (files.MAX_RESPONSE + 1)),
        httpx.Response(403, text="private error text"),
        httpx.Response(202, json={}),
        httpx.Response(302, headers={"Location": "https://other.invalid/"}),
    ],
)
def test_fail_closed_transport(reply, provider):
    requests = provider(lambda _: reply)
    res = _runner().invoke(main, [*ARGS, "f"])
    assert res.exit_code == 1 and not res.stdout_bytes and "private error text" not in res.stderr
    requests.assert_called_once()


def test_network_and_compression_fail_without_file_or_retry(provider):
    import gzip

    for handler in (
        lambda _: (_ for _ in ()).throw(httpx.ConnectError("private error text")),
        lambda _: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(b"{}")),
    ):
        requests = provider(handler)
        res = _runner().invoke(main, [*ARGS, "f"])
        assert res.exit_code == 1 and not res.stdout_bytes and "private error text" not in res.stderr
        requests.assert_called_once()


@pytest.mark.parametrize(
    "raw", [b"hello\x1b[2J", b"\x00", b"\x80", b"overwrite\rme", "x\u009by".encode(), "x\u202ey".encode()]
)
def test_unsafe_stdout_refused_even_when_piped(raw, provider):
    provider(lambda _: httpx.Response(200, json=record("f", raw)))
    res = _runner().invoke(main, [*ARGS, "f"])
    assert res.exit_code == 1 and not res.stdout_bytes and "--output" in res.stderr


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
def test_binary_output_exclusive_and_no_follow(provider, tmp_path):
    raw = b"\x00\xff\x1b\n"
    provider(lambda _: httpx.Response(200, json=record("f", raw)))
    dest = tmp_path / "out"
    runner = _runner()
    args = [*ARGS, "f", "-o", str(dest)]
    first = runner.invoke(main, args)
    assert first.exit_code == 0, first.output
    assert dest.read_bytes() == raw and dest.stat().st_mode & 0o077 == 0
    dest.write_bytes(b"keep")
    assert runner.invoke(main, args).exit_code == 1 and dest.read_bytes() == b"keep"
    symlink = tmp_path / "symlink"
    symlink.symlink_to(dest)
    assert runner.invoke(main, [*ARGS, "f", "-o", str(symlink)]).exit_code == 1
    symlink.unlink()
    symlink.symlink_to(tmp_path, target_is_directory=True)
    assert runner.invoke(main, [*ARGS, "f", "-o", str(symlink / "bad")]).exit_code == 1
    assert not (tmp_path / "bad").exists() and dest.read_bytes() == b"keep"


def test_local_global_target_and_direct_only(provider):
    req = provider(lambda _: httpx.Response(200, json=record("f", b"OK")))
    res = _runner().invoke(main, ["-R", "o/r", "repo", "read-file", "f"])
    assert res.exit_code == 0 and req.call_args.args[0].url.path == "/api/v5/repos/o/r/contents/f"
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["repo", "read-file", "f", "-R", "gitcode.com/o/r"])
    assert "read-file" in _runner().invoke(main, ["repo", "--help"]).output


@pytest.mark.parametrize(("token", "path"), [("bad\nsecret", "f"), ("synthetic-secret", "folder/synthetic-secret")])
def test_active_token_cannot_be_sent_in_url_or_with_header_controls(token, path, provider):
    req = provider(lambda _: pytest.fail("unexpected request"))
    res = _runner().invoke(main, ["--token", token, *ARGS, path])
    assert res.exit_code == 1 and "secret" not in res.stderr
    req.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
def test_failed_flush_never_leaves_visible_output(provider, tmp_path, monkeypatch):
    provider(lambda _: httpx.Response(200, json=record("f", b"file data")))
    dest = tmp_path / "out"

    def fail_fsync(_):
        assert not dest.exists()
        raise OSError(errno.ENOSPC, "simulated late write failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    result = _runner().invoke(main, [*ARGS, "f", "-o", str(dest)])
    assert result.exit_code == 1 and "Cannot save output" in result.stderr
    assert not dest.exists() and not list(tmp_path.glob(".gc-release-*"))


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
def test_competing_publish_is_preserved(provider, tmp_path, monkeypatch):
    provider(lambda _: httpx.Response(200, json=record("f", b"new data")))
    dest = tmp_path / "out"
    real_link = os.link

    def competing_link(*args, **kwargs):
        assert not dest.exists()
        dest.write_bytes(b"competitor")
        real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", competing_link)
    result = _runner().invoke(main, [*ARGS, "f", "-o", str(dest)])
    assert result.exit_code == 1 and "Output already exists" in result.stderr
    assert dest.read_bytes() == b"competitor" and not list(tmp_path.glob(".gc-release-*"))


@pytest.mark.parametrize("data", [b"", b"\0\xff\x1b[2J\r\n", b"x" * files.MAX_FILE], ids=["empty", "binary", "limit"])
def test_json_verifies_one_blob_and_content_is_explicit(data, provider):
    path = 'dir/棋 "1".png'
    row = record(path, data)

    def handle(req):
        assert req.method == "GET" and req.url.path == "/api/v5/repos/team/project/contents/" + path
        assert dict(req.url.params) == {"ref": "topic/assets"}
        assert req.headers["Authorization"] == "Bearer synthetic"
        return httpx.Response(200, json={**row, "gitSHA": "not-the-blob", "htmlUrl": "do not trust"})

    runner = _runner()
    args = ["--token", "synthetic", *ARGS, path, "--ref", "topic/assets", "--json"]
    req = provider(handle)
    metadata = runner.invoke(main, args)
    assert metadata.exit_code == 0, metadata.stderr
    assert list(json.loads(metadata.stdout_bytes).items()) == [
        ("name", '棋 "1".png'),
        ("path", path),
        ("gitSHA", row["sha"]),
        ("size", len(data)),
        ("type", "file"),
        ("encoding", "base64"),
    ]
    req.assert_called_once()
    req.reset_mock()

    projected = runner.invoke(main, [*args, "content, size,encoding"])
    assert projected.exit_code == 0, projected.stderr
    assert list(json.loads(projected.stdout_bytes).items()) == [
        ("content", row["content"]),
        ("size", len(data)),
        ("encoding", "base64"),
    ]
    assert b"\x1b" not in projected.stdout_bytes and projected.stdout_bytes.endswith(b"\n")
    req.assert_called_once()


@pytest.mark.parametrize(
    "options",
    [
        ["--json", "gitUrl"],
        ["--json", "path,downloadUrl"],
        ["--json", "private-selector"],
        ["--json="],
        ["--json", "path,"],
        ["--json", "size, size"],
        ["--json", "name", "--json", "path"],
        ["--json", "path", "--jq", ".path"],
        ["--json", "path", "--template", "{{.path}}"],
    ],
)
def test_invalid_json_before_target_or_fetch(options, provider, monkeypatch):
    target = Mock(side_effect=AssertionError("invalid selector should not resolve target"))
    monkeypatch.setattr("gitcode_cli.commands.repo._read_target", target)
    req = provider(lambda _: pytest.fail("unexpected request"))
    res = _runner().invoke(main, ["repo", "read-file", "f", *options])
    assert res.exit_code == 2 and not res.stdout_bytes and "private-selector" not in res.stderr
    target.assert_not_called()
    req.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_json_and_file_are_mutually_exclusive_before_any_read_or_write(tmp_path, provider, existing):
    dest = tmp_path / "out"
    if existing:
        dest.write_bytes(b"keep")
    req = provider(lambda _: pytest.fail("unexpected request"))
    res = _runner().invoke(main, [*ARGS, "f", "-o", str(dest), "--json"])
    assert res.exit_code == 2 and not res.stdout_bytes and "--json and --output" in res.stderr
    if existing:
        assert dest.read_bytes() == b"keep"
    else:
        assert not dest.exists()
    req.assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"type": "dir"},
        {"name": "other"},
        {"path": "elsewhere"},
        {"sha": "0" * 40},
        {"size": True},
        {"size": files.MAX_FILE + 1},
        {"encoding": "none"},
        {"content": "Yh=="},
    ],
)
def test_metadata_rejects_invalid_unselected_blob_fields(provider, updates):
    req = provider(lambda _: httpx.Response(200, json={**record("f", b"a"), **updates}))
    res = _runner().invoke(main, [*ARGS, "f", "--json", "path"])
    assert res.exit_code == 1 and not res.stdout_bytes
    req.assert_called_once()


@pytest.mark.parametrize(
    ("token", "path", "data", "field"),
    [
        ("synthetic-only", "f", b"prefix synthetic-only suffix", "content"),
        ("synthetic/only", "f", b"prefix synthetic%2Fonly suffix", "content"),
        ("c3ludGhldGlj", "f", b"synthetic", "content"),
        (r"z\"x", 'z"x', b"", "name"),
    ],
)
def test_json_does_not_echo_authentication(token, path, data, field, provider):
    req = provider(lambda _: httpx.Response(200, json=record(path, data)))
    res = _runner().invoke(main, ["--token", token, *ARGS, path, "--json", field])
    assert res.exit_code == 1 and not res.stdout_bytes and token not in res.stderr
    req.assert_called_once()


def test_json_fields_discoverable_without_proxy_mapping():
    help_text = _runner().invoke(main, ["repo", "read-file", "--help"]).output
    assert "--json" in help_text and "JSON FIELDS" in help_text and "gitSHA" in help_text
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["repo", "read-file", "f", "-R", "gitcode.com/o/r", "--json", "size"])


@pytest.mark.parametrize(
    "options",
    [
        ["--clobber"],
        ["--json", "path", "--clobber"],
        ["--json", "path", "-o", "out", "--clobber"],
        ["--clobber", "-o", "snapshot/"],
        ["--clobber", "-o", "snapshot/."],
        ["--clobber", "-o", ".."],
    ],
)
def test_clobber_requires_explicit_file_before_fetch(options, provider, monkeypatch):
    target = Mock(side_effect=AssertionError("invalid options should not resolve target"))
    monkeypatch.setattr("gitcode_cli.commands.repo._read_target", target)
    req = provider(lambda _: pytest.fail("unexpected request"))
    result = _runner().invoke(main, [*ARGS, "f", *options])
    assert result.exit_code == 2 and not result.stdout_bytes and "--" in result.stderr
    target.assert_not_called()
    req.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
@pytest.mark.parametrize("existing", [False, True])
def test_clobber_installs_exact_bytes_as_a_private_new_file(provider, tmp_path, existing):
    dest, alias = tmp_path / "snapshot", tmp_path / "original-hardlink"
    if existing:
        dest.write_bytes(b"original")
        dest.chmod(0o644)
        os.link(dest, alias)

    raw = b"\0\xff\n\x1b"
    req = provider(lambda _: httpx.Response(200, json=record("f", raw)))
    result = _runner().invoke(main, [*ARGS, "f", "--ref", "main", "--clobber", "-o", str(dest)])
    assert result.exit_code == 0, result.stderr
    assert not result.stdout_bytes and dest.read_bytes() == raw and dest.stat().st_mode & 0o077 == 0
    if existing:
        assert alias.read_bytes() == b"original" and not dest.samefile(alias)
    req.assert_called_once()
    request = req.call_args.args[0]
    assert request.method == "GET" and request.url.path == "/api/v5/repos/team/project/contents/f"
    assert dict(request.url.params) == {"ref": "main"}


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
@pytest.mark.parametrize("kind", ["directory", "symlink", "dangling", "linked-parent", "fifo"])
def test_clobber_refuses_nonregular_or_linked_destination(provider, tmp_path, kind):
    dest, original = tmp_path / "dest", tmp_path / "original"
    original.write_bytes(b"keep")
    if kind == "directory":
        dest.mkdir()
    elif kind == "symlink":
        dest.symlink_to(original)
    elif kind == "dangling":
        dest.symlink_to(tmp_path / "absent")
    elif kind == "linked-parent":
        dest.symlink_to(tmp_path, target_is_directory=True)
    else:
        os.mkfifo(dest)

    req = provider(lambda _: httpx.Response(200, json=record("f", b"replacement")))
    path = dest / original.name if kind == "linked-parent" else dest
    result = _runner().invoke(main, [*ARGS, "f", "-o", str(path), "--clobber"])
    assert result.exit_code != 0 and not result.stdout_bytes
    assert original.read_bytes() == b"keep" and not (tmp_path / "absent").exists()
    if kind in ("symlink", "dangling", "linked-parent"):
        assert dest.is_symlink()
    elif kind == "directory":
        assert dest.is_dir() and not list(dest.iterdir())
    else:
        assert dest.is_fifo()
    assert not list(tmp_path.glob(".gc-release-*"))
    req.assert_called_once()


@pytest.mark.skipif(os.name != "posix", reason="strict local output is POSIX only")
@pytest.mark.parametrize("failure", ["http", "integrity", "fsync", "replace"])
def test_clobber_failure_does_not_truncate_or_unlink_existing_file(provider, tmp_path, monkeypatch, failure):
    dest = tmp_path / "snapshot"
    dest.write_bytes(b"keep")
    identity = dest.stat().st_ino
    row = record("f", b"replacement")
    if failure == "integrity":
        row["sha"] = "0" * 40
    if failure in {"fsync", "replace"}:

        def fail(*_args, **_kwargs):
            assert dest.read_bytes() == b"keep" and dest.stat().st_ino == identity
            raise OSError(errno.EIO, "simulated filesystem failure")

        monkeypatch.setattr(os, failure, fail)
    req = provider(lambda _: httpx.Response(403 if failure == "http" else 200, json=row))
    result = _runner().invoke(main, [*ARGS, "f", "--clobber", "-o", str(dest)])
    assert result.exit_code == 1 and not result.stdout_bytes
    assert dest.read_bytes() == b"keep" and dest.stat().st_ino == identity
    assert not list(tmp_path.glob(".gc-release-*"))
    req.assert_called_once()
