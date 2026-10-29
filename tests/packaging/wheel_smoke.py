"""Build/install with normal registry access, then check a clean wheel offline.

The Python audit guard detects accidental network/native-process use in this
trusted CLI smoke. It is not an OS sandbox for hostile Python/native extensions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path

READY = "GC_WHEEL_GUARD_READY\n"
BLOCKED = "GC_WHEEL_OFFLINE_OPERATION_BLOCKED"
GUARD = """import os
import sys

def deny_external_operation(event, args):
    if event.startswith("socket.") or event in {
        "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork",
        "os.forkpty", "ctypes.dlopen", "ctypes.dlsym",
    }:
        os.write(2, b"GC_WHEEL_OFFLINE_OPERATION_BLOCKED\\n")
        raise RuntimeError("GC_WHEEL_OFFLINE_OPERATION_BLOCKED")

sys.addaudithook(deny_external_operation)
os.write(2, b"GC_WHEEL_GUARD_READY\\n")
"""
PROBE = """import json
import socket
import subprocess
import sys

blocked = []
for name, action in (
    ("dns", lambda: socket.getaddrinfo("offline.invalid", 443)),
    ("tcp", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)),
    ("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)),
    ("native_child", lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)),
):
    try:
        action()
    except RuntimeError as exc:
        assert str(exc) == "GC_WHEEL_OFFLINE_OPERATION_BLOCKED"
        blocked.append(name)
    else:
        raise AssertionError("offline guard did not reject " + name)
print(json.dumps(blocked))
"""
ARCHIVE_CHECK = """def confirm_archive_hash(archive, expected):
    assert isinstance(archive, dict), "missing wheel archive identity"
    if "hashes" in archive:
        hashes = archive["hashes"]
        assert isinstance(hashes, dict) and hashes.get("sha256") == expected, "wheel hash mismatch"
    else:
        assert archive.get("hash") == "sha256=" + expected, "missing or wrong legacy wheel hash"
    if "hash" in archive:
        assert archive["hash"] == "sha256=" + expected, "inconsistent legacy wheel hash"

"""
IDENTITY = (
    ARCHIVE_CHECK
    + """import hashlib
import importlib.metadata
import json
import pathlib
import sys

import gitcode_cli
import gitcode_cli.cli

expected = json.loads(sys.stdin.read())
prefix = pathlib.Path(sys.prefix).resolve()
checkout = pathlib.Path(expected["checkout"]).resolve()
assert prefix == pathlib.Path(expected["venv"]).resolve()
assert sys.prefix != sys.base_prefix
assert not sys.flags.optimize
assert "include-system-site-packages = false" in (prefix / "pyvenv.cfg").read_text().lower()
for item in sys.path:
    path = pathlib.Path(item or ".").resolve()
    assert path != checkout and checkout not in path.parents, "checkout leaked onto sys.path"
dist = importlib.metadata.distribution("pygitcode")
assert dist.version == expected["version"]
entrypoints = {e.name: e.value for e in dist.entry_points if e.group == "console_scripts"}
assert entrypoints == {"gc": "gitcode_cli.cli:main", "gitcode": "gitcode_cli.cli:main"}
direct = json.loads(dist.read_text("direct_url.json") or "{}")
assert not direct.get("dir_info", {}).get("editable", False)
confirm_archive_hash(direct.get("archive_info"), expected["sha256"])
package = pathlib.Path(gitcode_cli.__file__).resolve().parent
assert prefix in package.parents
actual = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in package.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
assert actual == expected["package_files"], "installed files differ from exact wheel"
for name, module in list(sys.modules.items()):
    if name == "gitcode_cli" or name.startswith("gitcode_cli."):
        origin = pathlib.Path(module.__file__).resolve()
        assert package == origin.parent or package in origin.parents
print(json.dumps({"version": dist.version, "package_files": len(actual), "entrypoints": sorted(entrypoints)}))
"""
)


def require(condition: bool, message: str) -> None:
    """Do not let optimized Python turn acceptance checks into no-ops."""
    if not condition:
        raise RuntimeError(message)


def wheel_manifest(wheel: Path, checkout: Path, tracked: set[str]) -> dict:
    """Bind package bytes to the wheel and current source, not another install."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate wheel paths")
        require(all(not n.startswith("/") and ".." not in Path(n).parts for n in names), "unsafe wheel path")
        metadata = [n for n in names if n.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "expected one wheel distribution")
        headers = BytesParser().parsebytes(archive.read(metadata[0]))
        require(headers["Name"] == "pygitcode" and bool(headers["Version"]), "unexpected wheel metadata")
        package = {}
        for name in names:
            if name.startswith("gitcode_cli/") and not name.endswith("/"):
                relative = name.removeprefix("gitcode_cli/")
                data = archive.read(name)
                source = checkout / "src" / name
                require("src/" + name in tracked, "wheel contains untracked source")
                require(source.is_file() and source.read_bytes() == data, "wheel/source bytes differ")
                package[relative] = hashlib.sha256(data).hexdigest()
        source_python = {path.removeprefix("src/gitcode_cli/") for path in tracked if path.endswith(".py")}
        require(bool(package) and source_python.issubset(package), "wheel omitted Python source")
    return {
        "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "version": headers["Version"],
        "package_files": package,
    }


def runtime_environment(root: Path) -> dict[str, str]:
    """Allowlist runtime settings, never ambient secrets, proxies or Python paths."""
    for name in ("home", "tmp", "work"):
        (root / name).mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update(
        {
            "PATH": os.defpath,
            "HOME": str(root / "home"),
            "USERPROFILE": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "home/.config"),
            "TMPDIR": str(root / "tmp"),
            "TMP": str(root / "tmp"),
            "TEMP": str(root / "tmp"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "NO_COLOR": "1",
            "COLUMNS": "120",
            "LC_ALL": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


def offline_run(command: list[str], root: Path, env: dict[str, str], *, input_text=None, probe=False):
    result = subprocess.run(
        command,
        cwd=root / "work",
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    require(result.stderr.startswith(READY), "offline guard did not load")
    result.stderr = result.stderr[len(READY) :]
    if not probe:
        require(BLOCKED not in result.stdout + result.stderr, "offline scenario attempted external operation")
    return result


def successful(result) -> str:
    require(result.returncode == 0 and result.stderr == "", "offline command failed")
    return result.stdout


def identity_output(result) -> str:
    """Report only numeric diagnostic metadata, never arbitrary child output."""
    if result.returncode != 0 or result.stderr:
        lines = re.findall(r'File "<string>", line ([0-9]+)', result.stderr)
        location = ",".join(lines[-3:]) or "unknown"
        raise RuntimeError(
            f"wheel identity failed (exit={result.returncode}, child_lines={location}, stderr={bool(result.stderr)})"
        )
    return result.stdout


def check_entrypoint(executable: Path, root: Path, env: dict[str, str], version: str) -> int:
    """Exercise each actual installed console script, with no module substitute."""
    require(executable.is_file() and not executable.is_symlink(), "missing console script")
    require(bool(executable.stat().st_mode & stat.S_IXUSR), "console script is not executable")
    shebang = executable.read_text(encoding="utf-8").splitlines()[0]
    require(shebang == "#!" + str(executable.parent / "python"), "console script uses another interpreter")
    count = 0
    for args in (["--help"], ["auth", "--help"], ["issue", "create", "--help"], ["pr", "create", "--help"]):
        output = successful(offline_run([str(executable), *args], root, env))
        require("USAGE" in output and "\x1b[" not in output, "invalid help output")
        count += 1
    for args, expected in (
        (["version"], f"gitcode version {version}\n"),
        (["--version"], f"gitcode, version {version}\n"),
    ):
        output = successful(offline_run([str(executable), *args], root, env))
        require(output == expected, "wrong wheel version")
        count += 1
    config = root / "home/.config/gc/config.json"
    before = offline_run([str(executable), "auth", "token"], root, env)
    require(before.returncode == 1 and before.stdout == "" and "No token found" in before.stderr, "unexpected token")
    token = "synthetic-wheel-token"
    login = successful(
        offline_run([str(executable), "auth", "login", "--with-token"], root, env, input_text=token + "\n")
    )
    require(login == "Authentication saved.\n", "unexpected login output")
    require(json.loads(config.read_text(encoding="utf-8")) == {"token": token}, "config roundtrip failed")
    require(stat.S_IMODE(config.stat().st_mode) == 0o600, "config is not private")
    require(successful(offline_run([str(executable), "auth", "token"], root, env)) == token + "\n", "token mismatch")
    override = {**env, "GC_TOKEN": "synthetic-wheel-env-token"}
    require(
        successful(offline_run([str(executable), "auth", "token"], root, override)) == "synthetic-wheel-env-token\n",
        "environment precedence failed",
    )
    require(json.loads(config.read_text(encoding="utf-8")) == {"token": token}, "override rewrote config")
    logout = successful(offline_run([str(executable), "auth", "logout"], root, env))
    require(logout == "Logged out.\n", "unexpected logout output")
    require(json.loads(config.read_text(encoding="utf-8")) == {}, "logout did not clear synthetic token")
    for args, code, message in (
        (["not-a-command"], 2, "No such command"),
        (["auth", "login", "--with-token"], 1, "No token provided on stdin"),
    ):
        result = offline_run([str(executable), *args], root, env, input_text="")
        require(result.returncode == code and result.stdout == "" and message in result.stderr, "wrong local error")
        require("Traceback" not in result.stderr, "unexpected traceback")
    return count + 7


def install_guard(python: Path, target: Path) -> None:
    """Load the audit hook from this venv, without adding a runtime PYTHONPATH."""
    result = subprocess.run(
        [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        cwd=target,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    purelib = Path(result.stdout.strip()).resolve(strict=True)
    require(target.resolve() in purelib.parents, "venv site-packages escaped its prefix")
    (purelib / "_gc_wheel_offline_guard.py").write_text(GUARD, encoding="utf-8")
    (purelib / "gc_wheel_offline_guard.pth").write_text("import _gc_wheel_offline_guard\n", encoding="utf-8")


def preparation(command: list[str], cwd: Path) -> None:
    # Registry/proxy configuration is intentionally preserved only in this phase.
    # Do not echo pip output, which can contain private registry locations.
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=300, check=False)
    require(result.returncode == 0, "wheel preparation failed (build/install; output withheld)")


def wheel_reference(wheel: Path, digest: str) -> str:
    """Give even older pip an explicit verified archive hash to record."""
    require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid wheel SHA-256")
    return wheel.resolve(strict=True).as_uri() + "#sha256=" + digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--temp-parent", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve(strict=True)
    temp_parent = args.temp_parent.resolve(strict=True)
    require(checkout != temp_parent and checkout not in temp_parent.parents, "temporary root must be outside checkout")
    require(len(args.source_sha) == 40 and all(c in "0123456789abcdef" for c in args.source_sha), "invalid source SHA")
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, timeout=20, check=True
    ).stdout.strip()
    require(actual == args.source_sha, "tested checkout SHA mismatch")
    clean = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--"], cwd=checkout, capture_output=True, timeout=20, check=False
    )
    require(clean.returncode == 0, "tracked checkout differs from tested SHA")
    tracked = set(
        subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", "src/gitcode_cli"],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        .stdout.rstrip("\0")
        .split("\0")
    )
    with tempfile.TemporaryDirectory(prefix="gc-wheel-", dir=temp_parent) as temporary:
        root = Path(temporary)
        wheelhouse = root / "wheels"
        wheelhouse.mkdir()
        preparation([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), "."], checkout)
        wheels = list(wheelhouse.glob("*.whl"))
        require(len(wheels) == 1, "expected exactly one freshly built wheel")
        manifest = wheel_manifest(wheels[0], checkout, tracked)
        target = root / "venv"
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(target)
        python = target / "bin/python"
        require(python.is_file(), "this CI smoke requires the POSIX venv layout")
        reference = wheel_reference(wheels[0], manifest["sha256"])
        preparation([str(python), "-m", "pip", "install", "--no-cache-dir", reference], root)
        install_guard(python, target)
        env = runtime_environment(root)
        probe = offline_run([str(python), "-c", PROBE], root, env, probe=True)
        require(probe.returncode == 0, "offline guard probe failed")
        require(json.loads(probe.stdout) == ["dns", "tcp", "udp", "native_child"], "incomplete guard probe")
        require(probe.stderr == (BLOCKED + "\n") * 4, "unexpected guard probe output")
        identity = {**manifest, "checkout": str(checkout), "venv": str(target)}
        installed = json.loads(
            identity_output(offline_run([str(python), "-c", IDENTITY], root, env, input_text=json.dumps(identity)))
        )
        scenarios = {
            name: check_entrypoint(target / "bin" / name, root, env, manifest["version"]) for name in ("gc", "gitcode")
        }
        print(
            json.dumps(
                {
                    "schema": "gc-clean-wheel-v1",
                    "source_sha": actual,
                    "python": sys.version.split()[0],
                    "wheel": manifest["wheel"],
                    "sha256": manifest["sha256"],
                    "version": installed["version"],
                    "package_files": installed["package_files"],
                    "guard_probes": 4,
                    "scenarios": scenarios,
                    "status": "passed",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
