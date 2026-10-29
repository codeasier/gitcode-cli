"""Release guards are exercised offline; no package upload or real API calls."""

import importlib.util
import io
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release_check.py"
SPEC = importlib.util.spec_from_file_location("release_check", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.fixture
def package(tmp_path):
    source = SCRIPT.parent.parent
    for filename in ("pyproject.toml", "src/gitcode_mcp/__init__.py", "CHANGELOG.md"):
        target = tmp_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / filename).read_bytes())
    project = tmp_path / "pyproject.toml"
    current = tomllib.loads(project.read_text())["project"]["version"]
    project.write_text(project.read_text().replace(f'version = "{current}"', 'version = "0.3.0"'))
    (tmp_path / "src/gitcode_mcp/__init__.py").write_text('__version__ = "0.3.0"\n')
    (tmp_path / "CHANGELOG.md").write_text("## [0.3.0]\n\nSynthetic release fixture.\n")
    return tmp_path


def test_checked_in_release_metadata_agrees(package):
    assert release.source_metadata(package, "mcp-v0.3.0")["version"] == "0.3.0"


@pytest.mark.parametrize("tag", ["v0.3.0", "mcp-v0.3.1", "mcp-v0.3.0rc1", "mcp-v0.3.0\n"])
def test_release_tag_must_match_exact_source_version(package, tag):
    with pytest.raises(ValueError, match="Tag must exactly match"):
        release.source_metadata(package, tag)


def test_import_version_cannot_disagree(package):
    (package / "src/gitcode_mcp/__init__.py").write_text('__version__ = "0.3.1"\n')
    with pytest.raises(ValueError, match="Source import version"):
        release.source_metadata(package)


@pytest.mark.parametrize("notes", ["# Changelog\n", "## [0.3.0]\n\n## [0.2.0]\nold\n"])
def test_release_notes_must_exist_and_be_nonempty(package, notes):
    (package / "CHANGELOG.md").write_text(notes)
    with pytest.raises(ValueError, match="release notes"):
        release.source_metadata(package)


@pytest.mark.parametrize("pin", ["pygitcode>=0.1.7", "pygitcode==0.1.6", "pygitcode==0.1.8"])
def test_dependency_pin_requires_separate_review(package, pin):
    path = package / "pyproject.toml"
    path.write_text(path.read_text().replace("pygitcode==0.1.7", pin))
    with pytest.raises(ValueError, match="CLI dependency"):
        release.source_metadata(package)


def archives(package, *, version=None, missing_requirement=False, cli=False, entries=None):
    project = release.source_metadata(package)
    dependencies = project["dependencies"][:-1] if missing_requirement else project["dependencies"]
    metadata = (
        "Metadata-Version: 2.3\n"
        f"Name: {project['name']}\n"
        f"Version: {version or project['version']}\n"
        f"Requires-Python: {project['requires-python']}\n"
        + "".join(f"Requires-Dist: {value}\n" for value in dependencies)
        + 'Requires-Dist: pytest>=8.3; extra == "dev"\n\n'
    ).encode()
    directory = package / "dist"
    directory.mkdir()
    info = "codeasier_gitcode_mcp-0.3.0.dist-info/"
    with zipfile.ZipFile(directory / "codeasier_gitcode_mcp-0.3.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr(info + "METADATA", metadata)
        wheel.writestr(
            info + "entry_points.txt",
            "[console_scripts]\n"
            + "".join(
                f"{name} = {value}\n" for name, value in (entries or release.ENTRY_POINTS).items()
            ),
        )
        wheel.writestr(info + "licenses/LICENSE", "MIT license, Codeasier")
        wheel.writestr("gitcode_mcp/__init__.py", "")
        if cli:
            wheel.writestr("gitcode_cli/__init__.py", "")
    with tarfile.open(directory / "codeasier_gitcode_mcp-0.3.0.tar.gz", "w:gz") as sdist:
        info = tarfile.TarInfo("codeasier_gitcode_mcp-0.3.0/PKG-INFO")
        info.size = len(metadata)
        sdist.addfile(info, io.BytesIO(metadata))
    return directory


def test_built_archives_preserve_independent_distribution_contract(package):
    release.check_archives(package, archives(package))


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"version": "0.3.1"}, "Archive version"),
        ({"missing_requirement": True}, "runtime requirements"),
        ({"cli": True}, "CLI must remain separate"),
        ({"entries": {"gc": "gitcode_cli.cli:main"}}, "Wheel entry points"),
    ],
)
def test_archive_contract_mismatch_fails_closed(package, options, message):
    directory = archives(package, **options)
    with pytest.raises(ValueError, match=message):
        release.check_archives(package, directory)


def test_stale_distribution_cannot_be_published_alongside_current(package):
    directory = archives(package)
    (directory / "stale.whl").write_bytes(b"not a wheel")
    with pytest.raises(ValueError, match="exactly one wheel"):
        release.check_archives(package, directory)


def test_non_distribution_artifacts_are_rejected(package):
    directory = archives(package)
    (directory / "state.sqlite3").touch()
    with pytest.raises(ValueError, match="Unexpected extra"):
        release.check_archives(package, directory)


SOURCE_SHA = "a" * 40


def test_manifest_binds_source_version_filenames_and_tested_bytes(package):
    directory = archives(package)
    manifest = package / "release-manifest.json"
    data = release.artifact_manifest(package, directory, SOURCE_SHA)
    manifest.write_text(json.dumps(data))
    release.verify_manifest(package, directory, manifest, SOURCE_SHA)
    assert data["source_sha"] == SOURCE_SHA and data["version"] == "0.3.0"
    assert all(len(digest) == 64 for digest in data["files"].values())


@pytest.mark.parametrize("mutation", ["bytes", "source", "version", "extra_key"])
def test_manifest_rejects_modified_bytes_or_context(package, mutation):
    directory = archives(package)
    manifest = package / "release-manifest.json"
    data = release.artifact_manifest(package, directory, SOURCE_SHA)
    if mutation == "bytes":
        with zipfile.ZipFile(next(directory.glob("*.whl")), "a") as wheel:
            wheel.writestr("extra.txt", "modified after acceptance")
    elif mutation == "source":
        data["source_sha"] = "b" * 40
    elif mutation == "version":
        data["version"] = "0.3.1"
    else:
        data["ignored"] = "unexpected"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity mismatch"):
        release.verify_manifest(package, directory, manifest, SOURCE_SHA)


def test_manifest_refuses_renamed_distributions(package):
    directory = archives(package)
    next(directory.glob("*.whl")).rename(directory / "unrelated.whl")
    with pytest.raises(ValueError, match="artifact filenames"):
        release.artifact_manifest(package, directory, SOURCE_SHA)
