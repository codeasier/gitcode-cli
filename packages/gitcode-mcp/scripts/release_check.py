"""Validate independent MCP release sources and built archives without publication."""

from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PACKAGE = "codeasier-gitcode-mcp"
ENTRY_POINTS = {
    "gitcode-mcp": "gitcode_mcp.__main__:main",
    "gitcode-clone": "gitcode_mcp.clone:main",
}
STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_metadata(package: Path, tag: str | None = None) -> dict:
    project = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    require(project["name"] == PACKAGE, "Unexpected distribution name")
    require(bool(STABLE_VERSION.fullmatch(version)), "Only stable X.Y.Z MCP versions are supported")
    if tag is not None:
        require(tag == "mcp-v" + version, "Tag must exactly match the checked-in MCP version")
    require(project["requires-python"] == ">=3.11", "Unexpected MCP Python compatibility")
    require(project["scripts"] == ENTRY_POINTS, "MCP entry points changed")
    require(
        "pygitcode==0.1.7" in project["dependencies"], "Review CLI dependency changes separately"
    )
    module = ast.parse((package / "src/gitcode_mcp/__init__.py").read_text(encoding="utf-8"))
    versions = [
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    ]
    require(versions == [version], "Source import version differs from distribution metadata")
    notes = (package / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", notes, re.M | re.S)
    require(
        match is not None and bool(match.group(1).strip()), "Missing nonempty MCP release notes"
    )
    return project


def requirements(values: list[str]) -> set[str]:
    result = set()
    for value in values:
        requirement = Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            result.add(str(requirement))
    return result


def check_metadata(content: bytes, project: dict) -> None:
    metadata = BytesParser().parsebytes(content)
    require(canonicalize_name(metadata["Name"] or "") == PACKAGE, "Wrong archive distribution")
    require(metadata["Version"] == project["version"], "Archive version differs from source")
    require(
        metadata["Requires-Python"] == project["requires-python"], "Archive Python floor differs"
    )
    require(
        requirements(metadata.get_all("Requires-Dist", []))
        == requirements(project["dependencies"]),
        "Archive runtime requirements differ from source",
    )


def check_archives(package: Path, directory: Path) -> None:
    project = source_metadata(package)
    wheels = list(directory.glob("*.whl"))
    sdists = list(directory.glob("*.tar.gz"))
    require(len(wheels) == len(sdists) == 1, "Expected exactly one wheel and one sdist")
    require(len(list(directory.iterdir())) == 2, "Unexpected extra release artifacts")
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "Expected one wheel metadata record")
        check_metadata(wheel.read(metadata[0]), project)
        info = metadata[0].removesuffix("METADATA")
        entries = configparser.ConfigParser()
        entries.read_string(wheel.read(info + "entry_points.txt").decode("utf-8"))
        require(dict(entries["console_scripts"]) == ENTRY_POINTS, "Wheel entry points differ")
        require("gitcode_mcp/__init__.py" in names, "MCP import package is missing")
        require(
            not any(name.startswith("gitcode_cli/") for name in names), "CLI must remain separate"
        )
        licenses = [name for name in names if name.startswith(info) and name.endswith("/LICENSE")]
        require(bool(licenses), "Wheel license is missing")
        require(
            any(b"codeasier" in wheel.read(name).lower() for name in licenses),
            "License attribution missing",
        )
    with tarfile.open(sdists[0], "r:gz") as sdist:
        members = sdist.getmembers()
        records = [
            item
            for item in members
            if len(Path(item.name).parts) == 2 and item.name.endswith("/PKG-INFO")
        ]
        require(len(records) == 1 and records[0].isfile(), "Expected one sdist metadata record")
        stream = sdist.extractfile(records[0])
        require(stream is not None, "Missing sdist metadata")
        with stream:
            check_metadata(stream.read(), project)


def artifact_manifest(package: Path, directory: Path, source_sha: str) -> dict:
    project = source_metadata(package)
    require(bool(re.fullmatch(r"[0-9a-f]{40}", source_sha)), "Expected a full source commit SHA")
    check_archives(package, directory)
    version = project["version"]
    names = {
        f"codeasier_gitcode_mcp-{version}-py3-none-any.whl",
        f"codeasier_gitcode_mcp-{version}.tar.gz",
    }
    require({path.name for path in directory.iterdir()} == names, "Unexpected artifact filenames")
    files = {}
    for name in sorted(names):
        path = directory / name
        require(path.is_file() and not path.is_symlink(), "Artifacts must be regular files")
        with path.open("rb") as stream:
            files[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "schema": 1,
        "package": PACKAGE,
        "version": version,
        "source_sha": source_sha,
        "files": files,
    }


def verify_manifest(package: Path, directory: Path, manifest: Path, source_sha: str) -> None:
    require(manifest.is_file() and not manifest.is_symlink(), "Missing regular integrity manifest")
    expected = artifact_manifest(package, directory, source_sha)
    require(
        json.loads(manifest.read_text(encoding="utf-8")) == expected,
        "Release artifact integrity mismatch",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("source", "artifacts", "manifest", "verify"))
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag")
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    project = source_metadata(args.package, args.tag)
    directory = args.dist or args.package / "dist"
    manifest = args.manifest or args.package / "release-manifest.json"
    if args.mode == "artifacts":
        check_archives(args.package, directory)
    elif args.mode in {"manifest", "verify"}:
        if args.source_sha is None:
            parser.error("manifest and verify require --source-sha")
        if args.mode == "manifest":
            value = artifact_manifest(args.package, directory, args.source_sha)
            manifest.write_text(
                json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
        else:
            verify_manifest(args.package, directory, manifest, args.source_sha)
    print(project["version"])


if __name__ == "__main__":
    main()
