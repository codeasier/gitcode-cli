"""Accept the reviewed PyPI CLI bytes, not a sibling checkout or rebuilt substitute.

Downloads/installations run only in CI. The test mode runs the complete MCP suite
and explicit FileService contracts against the selected installed archive.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import socket
import sys
import sysconfig
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.1.7"
SOURCE_SHA = "2f110178d754299214dcdbd94ce41788eb2044ab"
SOURCE_PATHS = {
    "gitcode_cli/__init__.py",
    "gitcode_cli/client.py",
    "gitcode_cli/services/__init__.py",
    "gitcode_cli/services/files.py",
    "gitcode_cli/services/issues.py",
    "gitcode_cli/services/pulls.py",
    "gitcode_cli/services/repos.py",
    "gitcode_cli/services/users.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        require(key not in value, "Duplicate manifest key")
        value[key] = item
    return value


def exact_keys(value: object, expected: set[str]) -> None:
    require(isinstance(value, dict) and set(value) == expected, "Unexpected manifest fields")


def is_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    exact_keys(data, {"schema", "package", "version", "source_sha", "artifacts", "source_files"})
    require(type(data["schema"]) is int and data["schema"] == 1, "Unknown manifest schema")
    require(data["package"] == "pygitcode", "Unexpected CLI distribution")
    require(data["version"] == VERSION, "Unreviewed CLI version")
    require(data["source_sha"] == SOURCE_SHA, "Unreviewed CLI source commit")
    exact_keys(data["artifacts"], {"wheel", "sdist"})
    for kind, suffix in (("wheel", "-py3-none-any.whl"), ("sdist", ".tar.gz")):
        artifact = data["artifacts"][kind]
        exact_keys(artifact, {"filename", "url", "sha256", "size"})
        filename = f"pygitcode-{VERSION}{suffix}"
        require(artifact["filename"] == filename, "Unexpected artifact filename")
        require(isinstance(artifact["url"], str), "Invalid official artifact URL")
        url = urlsplit(artifact["url"])
        require(
            url.scheme == "https"
            and url.netloc == "files.pythonhosted.org"
            and re.fullmatch(
                r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/" + re.escape(filename),
                url.path,
            )
            is not None
            and not url.query
            and not url.fragment,
            "Invalid official artifact URL",
        )
        require(is_digest(artifact["sha256"]), "Invalid artifact SHA256")
        require(
            type(artifact["size"]) is int and 0 < artifact["size"] < 1_000_000,
            "Invalid artifact size",
        )
    exact_keys(data["source_files"], SOURCE_PATHS)
    require(
        all(is_digest(value) for value in data["source_files"].values()), "Invalid source SHA256"
    )
    return data


def verify_bytes(content: bytes, artifact: dict) -> None:
    require(len(content) == artifact["size"], "Artifact size mismatch")
    require(hashlib.sha256(content).hexdigest() == artifact["sha256"], "Artifact SHA256 mismatch")


def archive_path(data: dict, kind: str, directory: Path) -> Path:
    require(kind in data["artifacts"], "Unknown artifact kind")
    artifact = data["artifacts"][kind]
    require(not directory.is_symlink() and directory.is_dir(), "Missing regular artifact directory")
    require(
        {item.name for item in directory.iterdir()} == {artifact["filename"]},
        "Unexpected artifact directory entries",
    )
    path = directory / artifact["filename"]
    require(path.is_file() and not path.is_symlink(), "Artifact must be a regular file")
    verify_bytes(path.read_bytes(), artifact)
    return path.resolve()


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Artifact download redirects are not allowed")


def download(data: dict, kind: str, directory: Path) -> Path:
    require(kind in data["artifacts"], "Unknown artifact kind")
    require(not directory.is_symlink(), "Artifact directory cannot be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    require(not list(directory.iterdir()), "Artifact directory must be empty")
    artifact = data["artifacts"][kind]
    opener = urllib.request.build_opener(NoRedirects())
    with opener.open(artifact["url"], timeout=30) as response:
        require(response.geturl() == artifact["url"], "Artifact URL changed")
        content = response.read(artifact["size"] + 1)
    verify_bytes(content, artifact)
    with (directory / artifact["filename"]).open("xb") as stream:
        stream.write(content)
    return archive_path(data, kind, directory)


def verify_direct_url(value: str | None, archive: Path, artifact: dict) -> None:
    require(value is not None, "Missing CLI direct_url installation provenance")
    direct = json.loads(value)
    require(
        set(direct) == {"url", "archive_info"},
        "CLI install must be an archive, never editable/VCS",
    )
    require(direct["url"] == archive.as_uri(), "CLI was not installed from the selected archive")
    info = direct["archive_info"]
    require(
        isinstance(info, dict) and info.get("hashes", {}).get("sha256") == artifact["sha256"],
        "Installed archive digest mismatch",
    )


def verify_installed(data: dict, kind: str, directory: Path, checkout: Path) -> None:
    archive = archive_path(data, kind, directory)
    require(sys.flags.isolated == 1, "Use python -I for installed acceptance")
    require(sys.prefix != sys.base_prefix, "A clean virtual environment is required")
    require("PYTHONPATH" not in os.environ, "PYTHONPATH must not be inherited")
    checkout = checkout.resolve()
    require(not Path.cwd().resolve().is_relative_to(checkout), "Run outside the checkout")
    require(
        all(
            entry
            and Path(entry).resolve() != Path.cwd().resolve()
            and not Path(entry).resolve().is_relative_to(checkout)
            for entry in sys.path
        ),
        "Checkout/cwd cannot be on sys.path",
    )
    distributions = [
        item
        for item in importlib.metadata.distributions()
        if re.sub(r"[-_.]+", "-", item.metadata["Name"] or "").lower() == "pygitcode"
    ]
    require(len(distributions) == 1, "Expected one installed CLI distribution")
    distribution = distributions[0]
    require(distribution.version == data["version"], "Installed CLI version mismatch")
    installed = Path(distribution.locate_file("")).resolve()
    roots = {Path(sysconfig.get_path(name)).resolve() for name in ("purelib", "platlib")}
    require(
        installed in roots and installed.is_relative_to(Path(sys.prefix).resolve()),
        "CLI distribution is outside the clean venv",
    )
    verify_direct_url(distribution.read_text("direct_url.json"), archive, data["artifacts"][kind])
    records = {str(item) for item in distribution.files or ()}
    require(SOURCE_PATHS <= records, "Installed CLI file records are incomplete")
    services = installed / "gitcode_cli/services"
    actual = {"gitcode_cli/__init__.py", "gitcode_cli/client.py"} | {
        path.relative_to(installed).as_posix() for path in services.rglob("*.py")
    }
    require(actual == SOURCE_PATHS, "Installed service file set differs from the reviewed release")
    for relative, digest in data["source_files"].items():
        path = installed / relative
        require(
            path.is_file() and not path.is_symlink() and path.resolve() == path,
            "Installed source must be regular and inside the distribution",
        )
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            f"Installed source digest mismatch: {relative}",
        )
        module_name = relative.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        module = importlib.import_module(module_name)
        require(
            Path(module.__file__).resolve() == path,
            f"Imported source origin mismatch: {module_name}",
        )
    require(
        importlib.import_module("gitcode_cli").__version__ == data["version"],
        "CLI import version mismatch",
    )
    mcp = importlib.metadata.distribution("codeasier-gitcode-mcp")
    require(
        f"pygitcode=={VERSION}" in (mcp.requires or ()), "MCP must pin the reviewed published CLI"
    )
    mcp_origin = Path(importlib.import_module("gitcode_mcp").__file__).resolve()
    require(
        mcp_origin == Path(mcp.locate_file("gitcode_mcp/__init__.py")).resolve()
        and mcp_origin.is_relative_to(installed),
        "MCP must also be a non-editable venv installation",
    )


def no_network(*args, **kwargs):
    raise RuntimeError("Published CLI acceptance forbids socket networking")


def run_tests(data: dict, kind: str, directory: Path, package: Path) -> int:
    import pytest

    checkout = package.parents[1]
    verify_installed(data, kind, directory, checkout)
    # MockTransport and in-process ASGI tests need no connects. Keep socketpair
    # available for asyncio; reject real network connects (including DNS).
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", no_network)
        patch.setattr(socket.socket, "connect_ex", no_network)
        patch.setattr(socket.socket, "sendto", no_network)
        patch.setattr(socket, "create_connection", no_network)
        patch.setattr(socket, "getaddrinfo", no_network)
        status = pytest.main(
            [
                "-c",
                str(package / "pyproject.toml"),
                "--import-mode=importlib",
                str(package / "tests"),
                str(package / "tests_source"),
            ]
        )
    verify_installed(data, kind, directory, checkout)
    if status == 0:
        print(
            f"Verified published pygitcode {VERSION} {kind}: eight source hashes and full MCP contracts"
        )
    return int(status)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("download", "test"))
    parser.add_argument("--kind", required=True, choices=("wheel", "sdist"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    package = args.package.resolve()
    data = load_manifest(package / "published-cli.json")
    if args.mode == "download":
        print(download(data, args.kind, args.directory))
        return 0
    return run_tests(data, args.kind, args.directory, package)


if __name__ == "__main__":
    raise SystemExit(main())
