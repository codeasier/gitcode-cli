"""CI-only named-volume takeover and rollback with disposable synthetic OAuth state.

The host orchestrator uses the checked-in OAuth Compose files and upgrade guard.
It discovers the old container's actual volume, never derives its name from a
project prefix. Each server is stopped before another process opens its SQLite
database. Running-server probes use HTTP only, through container-local loopback.

All Docker commands are captured, never echoed with environment/configuration.
No production environment files, credentials, volumes or GitCode API are used.
The workflow's EXIT trap and the orchestrator's finally block clean only objects
carrying this invocation's random label. No artifacts contain the fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

LABEL = "io.codeasier.gitcode-mcp.volume-ci"
DATA = Path("/var/lib/gitcode-mcp")
DATABASE = DATA / "oauth.sqlite3"
MANIFEST = "synthetic-fixture.json"
HTTP_TOKENS = "synthetic-http-tokens.json"
SERVICE = "gitcode-mcp"
HELPER = "/checks/volume_acceptance.py"
LEGACY_SHA = "f93b67bb7048e556b44322d48664522f32651920"


class AcceptanceFailure(RuntimeError):
    """A fixed, credential-free failure description suitable for CI output."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def migration_helper():
    specification = importlib.util.spec_from_file_location(
        "migration_acceptance", "/checks/migration_acceptance.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def private_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as stream:
        os.chmod(stream.fileno(), 0o600)
        json.dump(value, stream)


def read_manifest() -> dict[str, Any]:
    manifest = json.loads((DATA / MANIFEST).read_text(encoding="utf-8"))
    require(manifest["legacy_sha"] == LEGACY_SHA, "Unexpected synthetic fixture provenance")
    require(
        manifest["fixture_format"] == "gitcode-mcp-migration-synthetic-v1",
        "Not a synthetic migration fixture",
    )
    return manifest


def prepare_fixture(uid: int, gid: int) -> None:
    """Runs only in the old image; its provider issues the original token pair."""
    import anyio

    helper = migration_helper()
    helper.isolate_process()
    helper.installed_metadata(legacy=True)  # Old image: MCP 0.3.0 with pygitcode 0.1.6.
    require(helper.VERSION == helper.LEGACY_VERSION, "Legacy fixture version changed")
    with tempfile.TemporaryDirectory(prefix="synthetic-oauth-") as temporary:
        fixture = Path(temporary) / "fixture"
        anyio.run(helper.seed, fixture)
        output = Path("/output")
        shutil.copyfile(fixture / "synthetic-oauth.sqlite3", output / "oauth.sqlite3")
        shutil.copyfile(fixture / MANIFEST, output / MANIFEST)
        manifest = json.loads((output / MANIFEST).read_text(encoding="utf-8"))
        configuration = {
            **manifest["configuration"],
            "GITCODE_MCP_ALLOWED_HOSTS": "migration.example.test",
            "GITCODE_MCP_ALLOWED_ORIGINS": "https://migration.example.test",
            "GITCODE_MCP_READ_ONLY": "false",
        }
        require(
            all("\n" not in value and "$" not in value for value in configuration.values()),
            "Unsafe synthetic env-file value",
        )
        (output / "synthetic.env").write_text(
            "".join(f"{key}={value}\n" for key, value in configuration.items()), encoding="utf-8"
        )
        for name in ("oauth.sqlite3", MANIFEST, "synthetic.env"):
            path = output / name
            path.chmod(0o600)
            os.chown(path, uid, gid)


def install_fixture() -> None:
    require(not list(DATA.iterdir()), "Refusing to seed a nonempty volume")
    for name in ("oauth.sqlite3", MANIFEST):
        path = DATA / name
        shutil.copyfile(Path("/input") / name, path)
        path.chmod(0o600)
        os.chown(path, 10001, 10001)
    DATA.chmod(0o700)
    os.chown(DATA, 10001, 10001)
    require(DATABASE.stat().st_size > 0, "Seeded database is empty")
    require(not (DATA / "synthetic-oauth.sqlite3").exists(), "Fixture uses the wrong database path")


def verify_stopped_database() -> None:
    """Called only after all server containers mounting this volume are stopped."""
    from cryptography.fernet import Fernet

    manifest = read_manifest()
    require(DATABASE.is_file(), "Compose database path does not contain the fixture")
    require(not (DATA / "synthetic-oauth.sqlite3").exists(), "An alternate database was tested")
    cipher = Fernet(manifest["configuration"]["GITCODE_MCP_OAUTH_ENCRYPTION_KEY"].encode())
    with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as connection:
        marker = connection.execute("SELECT value FROM oauth_metadata WHERE id = 1").fetchone()[0]
        rows = connection.execute("SELECT kind, key, value, expires FROM oauth_records").fetchall()
    require(
        cipher.decrypt(marker) == b"codeasier-gitcode-mcp.oauth-store.v1"
        and hashlib.sha256(marker).hexdigest() == manifest["marker_digest"],
        "Takeover or rollback rewrote the v1 marker or encryption key",
    )
    for kind, key, value, expires in rows:
        envelope = json.loads(cipher.decrypt(value))
        require(
            set(envelope) == {"kind", "key", "expires", "payload"}
            and (envelope["kind"], envelope["key"], envelope["expires"]) == (kind, key, expires),
            "Stored record envelope changed",
        )
    tokens = json.loads((DATA / HTTP_TOKENS).read_text(encoding="utf-8"))
    for kind, raw in (
        ("grant", manifest["grant_id"]),
        ("access", manifest["access_token"]),
        ("access", tokens["upgrade"]["access_token"]),
        ("refresh", tokens["rollback"]["refresh_token"]),
    ):
        require(
            any(row[:2] == (kind, hashlib.sha256(raw.encode()).hexdigest()) for row in rows),
            "Token or grant did not persist in the actual Compose database",
        )


def http_probe(phase: str) -> None:
    """Never opens SQLite or creates a second provider alongside a running server."""
    import httpx

    manifest = read_manifest()
    configuration = manifest["configuration"]
    public = configuration["GITCODE_MCP_PUBLIC_URL"]
    helper = migration_helper()
    with httpx.Client(
        base_url="http://127.0.0.1:8765",
        headers={"Host": "migration.example.test"},
        timeout=5,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        deadline = time.monotonic() + 30
        while True:
            try:
                response = client.get("/.well-known/oauth-authorization-server")
                if response.status_code == 200:
                    require(response.json()["token_endpoint"] == public + "/token", "Wrong issuer")
                    break
            except httpx.TransportError:
                pass
            require(time.monotonic() < deadline, "Service did not become HTTP-ready")
            time.sleep(0.2)

        def catalog(token: str) -> None:
            headers = {
                "Authorization": "Bearer " + token,
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            }
            initialized = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "synthetic-volume-ci", "version": "1"},
                    },
                },
            )
            require(initialized.status_code == 200, "Persisted access token was rejected")
            require(
                initialized.json()["result"]["serverInfo"]["version"] == helper.VERSION,
                "HTTP server version changed unexpectedly",
            )
            notified = client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            require(notified.status_code == 202, "HTTP initialization notification failed")
            response = client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            require(response.status_code == 200, "Authenticated tools/list failed")
            helper.check_catalog(response.json()["result"]["tools"])

        def refresh(token: str) -> dict[str, Any]:
            response = client.post(
                "/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token,
                    "client_id": configuration["GITCODE_MCP_OAUTH_CLIENT_ID"],
                    "client_secret": configuration["GITCODE_MCP_OAUTH_CLIENT_SECRET"],
                    "resource": public + "/mcp",
                },
            )
            require(response.status_code == 200, "Persisted refresh token was rejected")
            rotated = response.json()
            require(rotated["refresh_token"] != token, "HTTP refresh did not rotate the token")
            require(
                set(rotated["scope"].split()) == {"gitcode:read", "gitcode:write"},
                "HTTP refresh changed the grant scopes",
            )
            catalog(rotated["access_token"])
            return rotated

        require(client.post("/mcp", json={}).status_code == 401, "OAuth was not enforced")
        catalog(manifest["access_token"])
        if phase == "upgrade":
            tokens = {"upgrade": refresh(manifest["refresh_token"])}
            private_json(DATA / HTTP_TOKENS, tokens)
        elif phase == "rollback":
            tokens = json.loads((DATA / HTTP_TOKENS).read_text(encoding="utf-8"))
            catalog(tokens["upgrade"]["access_token"])
            tokens["rollback"] = refresh(tokens["upgrade"]["refresh_token"])
            private_json(DATA / HTTP_TOKENS, tokens)
        else:
            require(phase == "initial", "Unexpected HTTP probe phase")


class Docker:
    def __init__(self, run_id: str, home: Path):
        require(bool(re.fullmatch(r"[0-9a-f]{16}", run_id)), "Invalid cleanup scope")
        self.run_id = run_id
        self.environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "COMPOSE_DISABLE_ENV_FILE": "1",
        }

    def run(self, arguments: list[str], *, check: bool = True, timeout: int = 90, **environment):
        result = subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**self.environment, **environment},
        )
        if check:
            if result.returncode != 0:
                phase = arguments[0]
                if HELPER in arguments:
                    phase += "/" + arguments[arguments.index(HELPER) + 1]
                    # The controlled helper emits only fixed assertions or an
                    # exception class, never response bodies or token values.
                    safe_lines = [
                        line
                        for line in result.stderr.splitlines()
                        if line.startswith("Volume acceptance failed: ")
                        and line.isascii()
                        and line.isprintable()
                        and len(line) <= 250
                    ]
                    if safe_lines:
                        raise AcceptanceFailure(phase + ": " + safe_lines[-1])
                raise AcceptanceFailure(
                    f"Docker/Compose {phase} failed (exit {result.returncode}); raw output withheld"
                )
        return result

    def inspect(self, container: str, field: str):
        return json.loads(
            self.run(["inspect", "--format", "{{json " + field + "}}", container]).stdout
        )

    def no_live_mounts(self, volume: str) -> None:
        require(
            not self.run(["ps", "--quiet", "--filter", "volume=" + volume]).stdout.strip(),
            "Another running container still mounts the SQLite volume",
        )

    def cleanup(self) -> None:
        selector = f"label={LABEL}={self.run_id}"
        containers = self.run(["ps", "--all", "--quiet", "--filter", selector]).stdout.split()
        if containers:
            self.run(["rm", "--force", *containers])
        volumes = self.run(["volume", "ls", "--quiet", "--filter", selector]).stdout.split()
        if volumes:
            self.run(["volume", "rm", *volumes])


def container_mount(docker: Docker, container: str) -> str:
    require(
        docker.inspect(container, ".Config.User") == "10001:10001", "Service is not unprivileged"
    )
    require(
        docker.inspect(container, ".HostConfig.NetworkMode") == "none", "Network was not disabled"
    )
    require(
        not docker.inspect(container, ".HostConfig.PortBindings"), "Host ports were not removed"
    )
    require(docker.inspect(container, ".HostConfig.ReadonlyRootfs"), "Container root is writable")
    mounts = [
        mount for mount in docker.inspect(container, ".Mounts") if mount["Destination"] == str(DATA)
    ]
    require(len(mounts) == 1 and mounts[0]["Type"] == "volume", "OAuth mount is not a named volume")
    return mounts[0]["Name"]


def run_acceptance(root: Path, old_root: Path, old_image: str, new_image: str, run_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix="mcp-volume-ci-") as temporary:
        work = Path(temporary)
        docker = Docker(run_id, work)
        prefix = "mcpvol" + run_id
        helpers = [
            {
                "type": "bind",
                "source": str(root / "packages/gitcode-mcp/scripts" / name),
                "target": "/checks/" + name,
                "read_only": True,
            }
            for name in ("volume_acceptance.py", "migration_acceptance.py")
        ]
        base = root / "deploy/gitcode-mcp/compose.oauth.yaml"
        old_base = old_root / "deploy/gitcode-mcp/compose.oauth.yaml"
        upgrade = root / "deploy/gitcode-mcp/compose.oauth.upgrade.yaml"

        def helper(
            mode: str,
            *,
            volume: str | None = None,
            image: str = old_image,
            readonly: bool = False,
            extra: list[str] | None = None,
        ) -> None:
            arguments = [
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--read-only",
                "--name",
                prefix + "-helper",
                "--label",
                f"{LABEL}={run_id}",
                "--user",
                "0:0",
                "--cap-drop=ALL",
                "--cap-add=CHOWN",
                "--cap-add=DAC_OVERRIDE",
                "--cap-add=FOWNER",
                "--security-opt=no-new-privileges",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=16m",
            ]
            for mount in helpers:
                arguments += [
                    "--mount",
                    f"type=bind,src={mount['source']},dst={mount['target']},readonly",
                ]
            if mode == "prepare":
                arguments += ["--mount", f"type=bind,src={work},dst=/output"]
            if mode == "install":
                arguments += ["--mount", f"type=bind,src={work},dst=/input,readonly"]
            if volume:
                docker.no_live_mounts(volume)
                arguments += [
                    "--mount",
                    f"type=volume,src={volume},dst={DATA}" + (",readonly" if readonly else ""),
                ]
            docker.run([*arguments, image, "python", "-B", "-I", HELPER, mode, *(extra or [])])

        def compose(
            project: str,
            image: str,
            *,
            external: str | None = None,
            old: bool = False,
            arguments: list[str],
            check: bool = True,
        ):
            overlay = work / (project + ".yaml")
            overlay.write_text(
                "services:\n  gitcode-mcp:\n    image: "
                + json.dumps(image)
                + "\n    build: !reset null\n    ports: !reset []\n    network_mode: none\n"
                + "    restart: 'no'\n    labels: "
                + json.dumps({LABEL: run_id})
                + "\n    volumes: "
                + json.dumps(helpers)
                + "\n"
                + (
                    "volumes:\n  oauth-data:\n    labels: " + json.dumps({LABEL: run_id}) + "\n"
                    if external is None
                    else ""
                ),
                encoding="utf-8",
            )
            files = ["-f", str(old_base if old else base)]
            if external is not None:
                files += ["-f", str(upgrade)]
            return docker.run(
                [
                    "compose",
                    "--env-file",
                    str(work / "synthetic.env"),
                    "--project-name",
                    project,
                    *files,
                    "-f",
                    str(overlay),
                    *arguments,
                ],
                check=check,
                GITCODE_MCP_OAUTH_VOLUME_NAME=external or "",
            )

        def create(
            project: str, image: str, *, external: str | None = None, old: bool = False
        ) -> str:
            # Render and inspect the final model before creating any container.
            # It contains synthetic secrets, so never print the full JSON.
            configuration = json.loads(
                compose(
                    project,
                    image,
                    external=external,
                    old=old,
                    arguments=["config", "--format", "json"],
                ).stdout
            )
            service = configuration["services"][SERVICE]
            require(
                service.get("network_mode") == "none"
                and not service.get("ports")
                and not service.get("build")
                and service["environment"]["GITCODE_MCP_OAUTH_DATABASE"] == str(DATABASE),
                "Compose override did not isolate networking or use the exact database path",
            )
            if external is not None:
                configured_volume = configuration["volumes"]["oauth-data"]
                require(
                    configured_volume.get("external") is True
                    and configured_volume.get("name") == external,
                    "Upgrade did not declare the discovered volume as external",
                )
            compose(
                project,
                image,
                external=external,
                old=old,
                arguments=["create", "--no-build", "--pull", "never", SERVICE],
            )
            identifiers = compose(
                project,
                image,
                external=external,
                old=old,
                arguments=["ps", "--all", "--quiet", SERVICE],
            ).stdout.split()
            require(len(identifiers) == 1, "Expected exactly one Compose service container")
            container = identifiers[0]
            mounted = container_mount(docker, container)
            require(external is None or mounted == external, "Upgrade mounted a different volume")
            if external is not None:
                command = docker.inspect(container, ".Config.Cmd")
                require(
                    any("Upgrade refused:" in value for value in command),
                    "Upgrade guard was replaced",
                )
            return container

        def start(container: str, volume: str, phase: str) -> None:
            docker.no_live_mounts(volume)
            docker.run(["start", container])
            require(
                container_mount(docker, container) == volume, "Started container changed its volume"
            )
            docker.run(["exec", container, "python", "-B", "-I", HELPER, "http", phase], timeout=60)
            print("Passed: actual service HTTP " + phase, flush=True)

        def stop(container: str, volume: str) -> None:
            docker.run(["stop", "--time", "15", container])
            require(not docker.inspect(container, ".State.Running"), "Server did not stop")
            docker.no_live_mounts(volume)

        try:
            version = docker.run(["compose", "version", "--short"]).stdout
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
            require(
                match is not None and tuple(map(int, match.groups())) >= (2, 24, 4),
                "Compose >= 2.24.4 is required for isolated port-reset overrides",
            )
            helper("prepare", extra=[str(os.getuid()), str(os.getgid())])
            old_project, new_project = prefix + "old", prefix + "new"
            old_container = create(old_project, old_image, old=True)
            volume = container_mount(docker, old_container)  # Discover, do not guess.
            labels = json.loads(
                docker.run(
                    [
                        "volume",
                        "inspect",
                        "--format",
                        "{{json .Labels}}",
                        volume,
                    ]
                ).stdout
            )
            require(
                labels.get(LABEL) == run_id
                and labels.get("com.docker.compose.project") == old_project,
                "Discovered volume does not belong to this acceptance run",
            )
            helper("install", volume=volume)
            start(old_container, volume, "initial")
            stop(old_container, volume)
            new_container = create(new_project, new_image, external=volume)
            start(new_container, volume, "upgrade")
            stop(new_container, volume)
            start(old_container, volume, "rollback")
            stop(old_container, volume)
            helper("disk", volume=volume, image=new_image, readonly=True)
            print(
                "Passed: same discovered volume, sequential takeover/rollback, persisted v1 state",
                flush=True,
            )

            missing = prefix + "-missing"
            require(
                docker.run(["volume", "inspect", missing], check=False).returncode != 0,
                "Missing-volume negative control already exists",
            )
            rejected = compose(
                prefix + "missing",
                new_image,
                external=missing,
                arguments=["create", "--no-build", "--pull", "never", SERVICE],
                check=False,
            )
            require(rejected.returncode != 0, "Missing external volume was silently accepted")
            require(
                docker.run(["volume", "inspect", missing], check=False).returncode != 0,
                "Compose silently created the missing external volume",
            )

            empty = prefix + "-empty"
            docker.run(["volume", "create", "--label", f"{LABEL}={run_id}", empty])
            empty_container = create(prefix + "empty", new_image, external=empty)
            refusal = "Upgrade refused: the existing OAuth database is missing or empty."
            for condition in ("missing", "empty"):
                if condition == "empty":
                    helper("empty", volume=empty)
                docker.no_live_mounts(empty)
                previous_logs = docker.run(["logs", empty_container])
                previous_refusals = (previous_logs.stdout + previous_logs.stderr).count(refusal)
                docker.run(["start", empty_container])
                exit_code = docker.run(["wait", empty_container], timeout=30).stdout.strip()
                require(exit_code == "1", "Upgrade did not reject a missing/empty database")
                logs = docker.run(["logs", empty_container])
                require(
                    (logs.stdout + logs.stderr).count(refusal) > previous_refusals,
                    "Failed container did not execute the original upgrade refusal guard",
                )
                helper("check-empty", volume=empty, readonly=True, extra=[condition])
            print(
                "Passed: missing external volume and missing/empty database fail closed", flush=True
            )
        finally:
            docker.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("run", "cleanup", "prepare", "install", "http", "disk", "empty", "check-empty"),
    )
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    if args.mode == "run":
        require(
            len(args.arguments) == 5, "run requires source roots, image references and a run ID"
        )
        root, old_root, old_image, new_image, run_id = args.arguments

        # SIGTERM/INT enter finally; the workflow additionally has an EXIT trap.
        def interrupted(signum, frame):
            raise AcceptanceFailure("Acceptance interrupted")

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        run_acceptance(Path(root).resolve(), Path(old_root).resolve(), old_image, new_image, run_id)
    elif args.mode == "cleanup":
        require(len(args.arguments) == 1, "cleanup requires this invocation's run ID")
        with tempfile.TemporaryDirectory(prefix="mcp-volume-cleanup-") as home:
            Docker(args.arguments[0], Path(home)).cleanup()
    elif args.mode == "prepare":
        prepare_fixture(*map(int, args.arguments))
    elif args.mode == "install":
        install_fixture()
    elif args.mode == "http":
        http_probe(args.arguments[0])
    elif args.mode == "disk":
        verify_stopped_database()
    elif args.mode == "empty":
        require(not DATABASE.exists(), "Negative-control database already exists")
        DATABASE.touch(mode=0o600, exist_ok=False)
        os.chown(DATABASE, 10001, 10001)
    elif args.mode == "check-empty":
        require(not list(DATA.glob("*-journal")), "Rejected upgrade created a SQLite journal")
        require(
            (not DATABASE.exists())
            if args.arguments == ["missing"]
            else DATABASE.stat().st_size == 0,
            "Rejected upgrade initialized a new OAuth database",
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never expose subprocess output, response bodies or synthetic secrets.
        message = str(error) if isinstance(error, AcceptanceFailure) else type(error).__name__
        print("Volume acceptance failed: " + message, file=sys.stderr)
        raise SystemExit(1) from None
