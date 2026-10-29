"""Offline guard tests; actual artifact installation is a separate CI matrix."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "scripts/published_cli_acceptance.py"
SPEC = importlib.util.spec_from_file_location("published_cli_acceptance", SCRIPT)
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


@pytest.fixture
def manifest():
    return json.loads((PACKAGE / "published-cli.json").read_text())


def write_manifest(tmp_path, manifest):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_reviewed_manifest_has_exact_release_identity_and_eight_sources():
    value = acceptance.load_manifest(PACKAGE / "published-cli.json")
    assert value["version"] == "0.1.7"
    assert value["source_sha"] == "2f110178d754299214dcdbd94ce41788eb2044ab"
    assert len(value["source_files"]) == 8
    assert value["artifacts"]["wheel"]["sha256"] == (
        "923f5b0bf78275185e23e4fe3f982d504086927429a93f2de7c9226729e70e7e"
    )
    assert value["artifacts"]["sdist"]["sha256"] == (
        "455df55f49d40af1ff32d6c59671df97a47d0626d930ebcfe764d1574d26d575"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "schema",
        "bool_schema",
        "package",
        "version",
        "source",
        "extra_artifact",
        "missing_artifact",
        "extra_source",
        "missing_source",
        "source_digest",
    ],
)
def test_manifest_identity_and_file_set_fail_closed(tmp_path, manifest, mutation):
    if mutation == "unknown":
        manifest["ignored"] = True
    elif mutation == "schema":
        manifest["schema"] = 2
    elif mutation == "bool_schema":
        manifest["schema"] = True
    elif mutation == "package":
        manifest["package"] = "other"
    elif mutation == "version":
        manifest["version"] = "0.1.6"
    elif mutation == "source":
        manifest["source_sha"] = "a" * 40
    elif mutation == "extra_artifact":
        manifest["artifacts"]["extra"] = {}
    elif mutation == "missing_artifact":
        del manifest["artifacts"]["sdist"]
    elif mutation == "extra_source":
        manifest["source_files"]["gitcode_cli/services/extra.py"] = "a" * 64
    elif mutation == "missing_source":
        del manifest["source_files"]["gitcode_cli/services/files.py"]
    else:
        manifest["source_files"]["gitcode_cli/client.py"] = "not a digest"
    with pytest.raises(ValueError):
        acceptance.load_manifest(write_manifest(tmp_path, manifest))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("extra", True),
        ("filename", "../other.whl"),
        ("sha256", "F" * 64),
        ("size", True),
        ("size", 0),
        ("size", 1_000_000),
        ("url", "https://attacker.invalid/pygitcode.whl"),
        ("url", "https://files.pythonhosted.org@attacker.invalid/package"),
    ],
)
def test_artifact_fields_fail_closed(tmp_path, manifest, kind, key, value):
    manifest["artifacts"][kind][key] = value
    with pytest.raises(ValueError):
        acceptance.load_manifest(write_manifest(tmp_path, manifest))


@pytest.mark.parametrize("suffix", ["?mirror=other", "#fragment", "/extra"])
def test_official_url_cannot_select_another_resource(tmp_path, manifest, suffix):
    manifest["artifacts"]["wheel"]["url"] += suffix
    with pytest.raises(ValueError, match="official artifact URL"):
        acceptance.load_manifest(write_manifest(tmp_path, manifest))


def test_duplicate_manifest_keys_are_not_silently_accepted(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"schema": 1, "schema": 1}')
    with pytest.raises(ValueError, match="Duplicate manifest key"):
        acceptance.load_manifest(path)


@pytest.fixture
def synthetic_archive(tmp_path, manifest):
    value = copy.deepcopy(manifest)
    content = b"synthetic archive bytes, not an installable package"
    artifact = value["artifacts"]["wheel"]
    artifact.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())
    directory = tmp_path / "archives"
    directory.mkdir()
    path = directory / artifact["filename"]
    path.write_bytes(content)
    return value, directory, path


def test_exact_archive_bytes_and_direct_url_are_accepted(synthetic_archive):
    value, directory, path = synthetic_archive
    assert acceptance.archive_path(value, "wheel", directory) == path
    direct = {
        "url": path.as_uri(),
        "archive_info": {"hashes": {"sha256": value["artifacts"]["wheel"]["sha256"]}},
    }
    acceptance.verify_direct_url(json.dumps(direct), path, value["artifacts"]["wheel"])


@pytest.mark.parametrize("mutation", ["bytes", "size", "extra", "symlink", "directory_link"])
def test_archive_integrity_and_extra_files_fail_closed(synthetic_archive, mutation):
    value, directory, path = synthetic_archive
    if mutation == "bytes":
        path.write_bytes(b"x" * path.stat().st_size)
    elif mutation == "size":
        path.write_bytes(b"x")
    elif mutation == "extra":
        (directory / "extra.whl").touch()
    elif mutation == "symlink":
        target = directory.parent / "target"
        path.rename(target)
        path.symlink_to(target)
    else:
        link = directory.parent / "link"
        link.symlink_to(directory, target_is_directory=True)
        directory = link
    with pytest.raises(ValueError):
        acceptance.archive_path(value, "wheel", directory)


@pytest.mark.parametrize("mutation", ["missing", "editable", "vcs", "other_archive", "digest"])
def test_install_provenance_cannot_be_editable_or_another_archive(synthetic_archive, mutation):
    value, _, path = synthetic_archive
    artifact = value["artifacts"]["wheel"]
    direct = {"url": path.as_uri(), "archive_info": {"hashes": {"sha256": artifact["sha256"]}}}
    if mutation == "editable":
        direct["dir_info"] = {"editable": True}
    elif mutation == "vcs":
        direct["vcs_info"] = {"vcs": "git"}
    elif mutation == "other_archive":
        direct["url"] = (path.parent / "other.whl").as_uri()
    elif mutation == "digest":
        direct["archive_info"]["hashes"]["sha256"] = "a" * 64
    with pytest.raises(ValueError):
        acceptance.verify_direct_url(
            None if mutation == "missing" else json.dumps(direct), path, artifact
        )


def test_redirects_are_rejected_before_another_request():
    with pytest.raises(ValueError, match="redirects"):
        acceptance.NoRedirects().redirect_request(None, None, 302, "", {}, "https://other.invalid")


def test_download_reads_only_expected_size_and_checks_before_writing(
    tmp_path, manifest, monkeypatch
):
    content = b"synthetic download, never an installed package"
    artifact = manifest["artifacts"]["wheel"]
    artifact.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def geturl(self):
            return artifact["url"]

        def read(self, size):
            assert size == len(content) + 1
            return content

    class Opener:
        def open(self, url, timeout):
            assert url == artifact["url"] and timeout == 30
            return Response()

    monkeypatch.setattr(acceptance.urllib.request, "build_opener", lambda *args: Opener())
    path = acceptance.download(manifest, "wheel", tmp_path / "valid")
    assert path.read_bytes() == content
    artifact["sha256"] = "a" * 64
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        acceptance.download(manifest, "wheel", destination)
    assert list(destination.iterdir()) == []


def test_published_matrix_keeps_full_coverage_and_no_publication_permissions():
    workflow = (PACKAGE.parents[1] / ".github/workflows/gitcode-mcp.yml").read_text()
    job = workflow.split("  published-cli:\n", 1)[1].split("\n  container:", 1)[0]
    assert "python-version: ['3.11', '3.12', '3.13']" in job
    assert "artifact: [wheel, sdist]" in job
    assert "--no-deps --force-reinstall" in job and "--no-cache-dir" in job
    assert "-m pip --isolated check" in job
    assert 'cd "$work/cwd"' in job and "env -i PATH=" in job
    assert " -e " not in job
    assert not any(
        value in job for value in ("secrets.", "id-token:", "environment:", "twine", "pypa/")
    )


@pytest.fixture
def synthetic_install(synthetic_archive, monkeypatch):
    data, directory, archive = synthetic_archive
    work = directory.parent
    checkout = work / "checkout"
    installed = work / "venv/lib/python/site-packages"
    modules = {}
    for relative in data["source_files"]:
        path = installed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# synthetic, never executed: {relative}\n".encode()
        path.write_bytes(content)
        data["source_files"][relative] = hashlib.sha256(content).hexdigest()
        name = relative.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        modules[name] = SimpleNamespace(__file__=str(path), __version__="0.1.7")
    mcp_path = installed / "gitcode_mcp/__init__.py"
    modules["gitcode_mcp"] = SimpleNamespace(__file__=str(mcp_path))
    direct = {
        "url": archive.as_uri(),
        "archive_info": {"hashes": {"sha256": data["artifacts"]["wheel"]["sha256"]}},
    }
    distribution = SimpleNamespace(
        metadata={"Name": "pygitcode"},
        version="0.1.7",
        locate_file=lambda path: installed / path,
        read_text=lambda name: json.dumps(direct),
        files=[Path(path) for path in data["source_files"]],
    )
    mcp = SimpleNamespace(requires=["pygitcode==0.1.7"], locate_file=lambda path: installed / path)
    monkeypatch.setattr(acceptance.importlib.metadata, "distributions", lambda: [distribution])
    monkeypatch.setattr(acceptance.importlib.metadata, "distribution", lambda name: mcp)
    original_import = acceptance.importlib.import_module
    monkeypatch.setattr(
        acceptance.importlib,
        "import_module",
        lambda name: modules[name] if name in modules else original_import(name),
    )
    monkeypatch.setattr(acceptance.sysconfig, "get_path", lambda name: str(installed))
    monkeypatch.setattr(
        acceptance,
        "sys",
        SimpleNamespace(
            flags=SimpleNamespace(isolated=1),
            prefix=str(work / "venv"),
            base_prefix=str(work / "base"),
            path=[str(installed)],
        ),
    )
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.chdir(work)
    return data, directory, checkout, installed, distribution, mcp, modules


def test_installed_verifier_checks_the_selected_archive_and_import_origins(synthetic_install):
    data, directory, checkout, *_ = synthetic_install
    acceptance.verify_installed(data, "wheel", directory, checkout)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "bytes",
        "extra_service",
        "missing_source",
        "module_origin",
        "mcp_origin",
        "pin",
        "pythonpath",
        "sys_path",
        "cwd_on_path",
        "cwd",
        "duplicate_distribution",
    ],
)
def test_installed_source_and_import_contamination_fail_closed(
    synthetic_install, monkeypatch, mutation
):
    data, directory, checkout, installed, distribution, mcp, modules = synthetic_install
    if mutation == "version":
        distribution.version = "0.1.6"
    elif mutation == "bytes":
        (installed / "gitcode_cli/client.py").write_text("# changed")
    elif mutation == "extra_service":
        (installed / "gitcode_cli/services/extra.py").touch()
    elif mutation == "missing_source":
        (installed / "gitcode_cli/services/files.py").unlink()
    elif mutation == "module_origin":
        modules["gitcode_cli.client"].__file__ = str(checkout / "src/gitcode_cli/client.py")
    elif mutation == "mcp_origin":
        modules["gitcode_mcp"].__file__ = str(
            checkout / "packages/gitcode-mcp/src/gitcode_mcp/__init__.py"
        )
    elif mutation == "pin":
        mcp.requires = ["pygitcode==0.1.6"]
    elif mutation == "pythonpath":
        monkeypatch.setenv("PYTHONPATH", str(checkout / "src"))
    elif mutation == "sys_path":
        monkeypatch.setattr(acceptance.sys, "path", [str(checkout / "src")])
    elif mutation == "cwd_on_path":
        monkeypatch.setattr(acceptance.sys, "path", [str(Path.cwd())])
    elif mutation == "cwd":
        checkout.mkdir()
        monkeypatch.chdir(checkout)
    else:
        monkeypatch.setattr(
            acceptance.importlib.metadata, "distributions", lambda: [distribution, distribution]
        )
    with pytest.raises(ValueError):
        acceptance.verify_installed(data, "wheel", directory, checkout)


@pytest.mark.parametrize("status", [0, 1])
def test_full_suite_runs_between_same_process_verifications(
    manifest, tmp_path, monkeypatch, status, capsys
):
    events = []
    monkeypatch.setattr(acceptance, "verify_installed", lambda *args: events.append("verify"))

    def run(arguments):
        events.append("test")
        assert arguments == [
            "-c",
            str(PACKAGE / "pyproject.toml"),
            "--import-mode=importlib",
            str(PACKAGE / "tests"),
            str(PACKAGE / "tests_source"),
        ]
        with pytest.raises(RuntimeError, match="forbids socket"):
            acceptance.socket.create_connection(("api.gitcode.com", 443))
        return status

    monkeypatch.setattr(pytest, "main", run)
    assert acceptance.run_tests(manifest, "wheel", tmp_path, PACKAGE) == status
    assert events == ["verify", "test", "verify"]
    assert ("full MCP contracts" in capsys.readouterr().out) == (status == 0)
