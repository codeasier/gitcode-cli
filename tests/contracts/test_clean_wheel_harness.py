"""Offline guardrail contracts; actual build/install runs only in the CI smoke."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import zipfile
from pathlib import Path

import pytest

HELPER = Path(__file__).parents[1] / "packaging/wheel_smoke.py"
SPEC = importlib.util.spec_from_file_location("wheel_smoke", HELPER)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.mark.parametrize(
    "archive",
    [
        {"hashes": {"sha256": "a" * 64}},
        {"hash": "sha256=" + "a" * 64},
        {"hashes": {"sha256": "a" * 64}, "hash": "sha256=" + "a" * 64},
    ],
)
def test_archive_identity_accepts_modern_and_legacy_pip_metadata(archive):
    namespace = {}
    exec(smoke.ARCHIVE_CHECK, namespace)
    namespace["confirm_archive_hash"](archive, "a" * 64)
    assert smoke.IDENTITY.startswith(smoke.ARCHIVE_CHECK)


@pytest.mark.parametrize(
    "archive",
    [
        None,
        {},
        {"hashes": {"sha256": "b" * 64}},
        {"hash": "sha256=" + "b" * 64},
        {"hash": "md5=" + "a" * 64},
        {"hashes": {}, "hash": "sha256=" + "a" * 64},
        {"hashes": None, "hash": "sha256=" + "a" * 64},
        {"hashes": {"sha256": "b" * 64}, "hash": "sha256=" + "a" * 64},
        {"hashes": {"sha256": "a" * 64}, "hash": "sha256=" + "b" * 64},
    ],
)
def test_archive_identity_rejects_missing_wrong_or_contradictory_hashes(archive):
    namespace = {}
    exec(smoke.ARCHIVE_CHECK, namespace)
    with pytest.raises(AssertionError):
        namespace["confirm_archive_hash"](archive, "a" * 64)


def test_runtime_environment_does_not_inherit_secrets_or_paths(tmp_path, monkeypatch):
    forbidden = {
        "GC_TOKEN": "synthetic-ambient-token",
        "GITHUB_TOKEN": "synthetic-github-token",
        "HTTP_PROXY": "http://proxy.invalid",
        "HTTPS_PROXY": "http://proxy.invalid",
        "ALL_PROXY": "http://proxy.invalid",
        "NO_PROXY": "*",
        "PYTHONPATH": "/synthetic/checkout/src",
        "PYTHONHOME": "/synthetic/python",
        "PYTHONOPTIMIZE": "2",
        "VIRTUAL_ENV": "/synthetic/editable-venv",
        "PIP_INDEX_URL": "https://registry.invalid",
        "GC_GH_PROXY_ACTIVE": "1",
    }
    for key, value in forbidden.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HOME", "/synthetic/private-home")
    monkeypatch.setenv("PATH", "/synthetic/ambient-bin")

    env = smoke.runtime_environment(tmp_path)

    assert not forbidden.keys() & env.keys()
    assert env["HOME"] == str(tmp_path / "home")
    assert env["USERPROFILE"] == env["HOME"]
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / "home/.config")
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PATH"] != "/synthetic/ambient-bin"
    assert all((tmp_path / part).is_dir() for part in ("home", "tmp", "work"))


def make_wheel(tmp_path, *, body=b"value = 1\n", members=None):
    checkout = tmp_path / "checkout"
    package = checkout / "src/gitcode_cli"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"value = 1\n")
    wheel = tmp_path / "pygitcode-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pygitcode-1.2.3.dist-info/METADATA", "Name: pygitcode\nVersion: 1.2.3\n")
        for name, data in members if members is not None else [("gitcode_cli/__init__.py", body)]:
            archive.writestr(name, data)
    return checkout, wheel


def test_wheel_manifest_binds_exact_source_and_archive(tmp_path):
    checkout, wheel = make_wheel(tmp_path)
    manifest = smoke.wheel_manifest(wheel, checkout, {"src/gitcode_cli/__init__.py"})
    assert manifest == {
        "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "version": "1.2.3",
        "package_files": {"__init__.py": hashlib.sha256(b"value = 1\n").hexdigest()},
    }


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([], "omitted Python source"),
        ([("gitcode_cli/__init__.py", b"stale")], "wheel/source bytes differ"),
        ([("../outside.py", b"bad")], "unsafe wheel path"),
        ([("/absolute.py", b"bad")], "unsafe wheel path"),
        ([("gitcode_cli/not_in_source.py", b"bad")], "untracked source"),
    ],
)
def test_wheel_manifest_rejects_stale_missing_or_unsafe_members(tmp_path, members, message):
    checkout, wheel = make_wheel(tmp_path, members=members)
    with pytest.raises(RuntimeError, match=message):
        smoke.wheel_manifest(wheel, checkout, {"src/gitcode_cli/__init__.py"})


@pytest.mark.parametrize(
    ("stdout", "stderr", "message"),
    [
        ("", "", "guard did not load"),
        ("", "Error in sitecustomize", "guard did not load"),
        ("", smoke.READY + smoke.BLOCKED, "attempted external operation"),
        (smoke.BLOCKED, smoke.READY, "attempted external operation"),
    ],
)
def test_offline_run_fails_closed_even_when_child_reports_success(tmp_path, monkeypatch, stdout, stderr, message):
    monkeypatch.setattr(
        smoke.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout, stderr)
    )
    with pytest.raises(RuntimeError, match=message):
        smoke.offline_run(["/synthetic/venv/bin/gc", "--help"], tmp_path, {})


def test_offline_run_uses_explicit_environment_workdir_and_streams(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 2, "", smoke.READY + "local error\n")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    env = {"HOME": str(tmp_path / "home")}
    command = ["/synthetic/venv/bin/gitcode", "not-a-command"]
    result = smoke.offline_run(command, tmp_path, env, input_text="")
    assert (result.returncode, result.stdout, result.stderr) == (2, "", "local error\n")
    assert calls[0][0] == command
    assert calls[0][1]["env"] is env
    assert calls[0][1]["cwd"] == tmp_path / "work"
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["timeout"] == 20
    assert calls[0][1]["input"] == ""


@pytest.mark.parametrize("code,stderr", [(1, ""), (0, "unexpected stderr")])
def test_successful_requires_zero_exit_and_empty_stderr(code, stderr):
    with pytest.raises(RuntimeError, match="offline command failed"):
        smoke.successful(subprocess.CompletedProcess([], code, "output", stderr))


def test_identity_failure_reports_only_exit_and_source_line():
    stderr = 'private-prefix\n  File "<string>", line 27, in <module>\nAssertionError: private-detail\n'
    with pytest.raises(RuntimeError, match=r"exit=1, child_lines=27, stderr=True") as error:
        smoke.identity_output(subprocess.CompletedProcess([], 1, "private-stdout", stderr))
    assert "private" not in str(error.value)


def test_identity_stderr_without_traceback_is_still_fatal():
    with pytest.raises(RuntimeError, match="exit=0, child_lines=unknown, stderr=True"):
        smoke.identity_output(subprocess.CompletedProcess([], 0, "", "private-warning"))


def test_identity_success_preserves_stdout():
    assert smoke.identity_output(subprocess.CompletedProcess([], 0, "identity", "")) == "identity"


@pytest.mark.parametrize("name", ["gc", "gitcode"])
def test_missing_entrypoint_fails_instead_of_skipping(tmp_path, name):
    with pytest.raises(RuntimeError, match="missing console script"):
        smoke.check_entrypoint(tmp_path / name, tmp_path, {}, "1.2.3")


def test_wrong_entrypoint_interpreter_fails_before_execution(tmp_path):
    executable = tmp_path / "gc"
    executable.write_text("#!/ambient/python\n", encoding="utf-8")
    executable.chmod(0o700)
    with pytest.raises(RuntimeError, match="another interpreter"):
        smoke.check_entrypoint(executable, tmp_path, {}, "1.2.3")


def test_failed_install_is_fatal_without_exposing_registry_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        smoke.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, b"private-registry-output", b"private-error"),
    )
    with pytest.raises(RuntimeError, match="wheel preparation failed") as error:
        smoke.preparation(["/synthetic/venv/bin/python", "-m", "pip", "install"], tmp_path)
    assert "private" not in str(error.value)


def test_guard_cannot_be_installed_outside_new_venv(tmp_path, monkeypatch):
    target = tmp_path / "venv"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(
        smoke.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, str(outside), "")
    )
    with pytest.raises(RuntimeError, match="escaped its prefix"):
        smoke.install_guard(target / "bin/python", target)
    assert not list(outside.iterdir())
