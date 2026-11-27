"""Real loopback TLS check for source CI; not part of installed offline acceptance."""

import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet

from gitcode_mcp import cli_oauth_service as svc


class DirectTLSIntegration(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        state = self.root / "state"
        state.mkdir(0o700)
        self.env = {
            "GC_CLI_BROKER_ENABLED": "1",
            "GC_CLI_BROKER_APP_ID": "fixture-app",
            "GC_CLI_BROKER_STATE_DIR": str(state),
        }
        for name, data in (
            ("APP_SECRET_FILE", b"fixture-app-private"),
            ("ENCRYPTION_KEY_FILE", Fernet.generate_key()),
        ):
            p = self.root / name
            p.touch(mode=0o600)
            p.write_bytes(data)
            self.env["GC_CLI_BROKER_" + name] = str(p)

    def test_direct_tls_process_and_silent_callback(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"https://127.0.0.1:{port}"
        cert, key = self.root / "TLS_CERT_FILE", self.root / "TLS_KEY_FILE"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        key.chmod(0o600)
        env = {
            "PATH": os.defpath,
            "HOME": str(self.root),
            "PYTHONPATH": str(Path(svc.__file__).parents[1]),
            **self.env,
            "GC_CLI_BROKER_ORIGIN": origin,
            "GC_CLI_BROKER_TLS_CERT_FILE": str(cert),
            "GC_CLI_BROKER_TLS_KEY_FILE": str(key),
            "SSLKEYLOGFILE": str(self.root / "keylog"),
            "HTTPS_PROXY": "http://127.0.0.1:1",
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "gitcode_mcp.cli_oauth_service"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            verify = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            verify.load_verify_locations(cafile=str(cert))
            with httpx.Client(base_url=origin, verify=verify, trust_env=False, timeout=0.6) as c:
                for _ in range(60):
                    if proc.poll() is not None:
                        self.fail("broker exited before TLS startup")
                    try:
                        response = c.get(svc.ENTRY)
                        break
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        time.sleep(0.05)
                else:
                    self.fail("broker never accepted TLS")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(c.get("/mcp").status_code, 404)
                self.assertNotEqual(
                    c.get(
                        svc.ENTRY,
                        headers={"host": "elsewhere", "x-forwarded-host": urlsplit(origin).netloc},
                    ).status_code,
                    200,
                )
                r = c.get(svc.CALLBACK, params={"code": "syntheticNeverLog"})
                self.assertEqual(r.status_code, 303)
                self.assertEqual(r.headers["location"], svc.FINISHED)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
            try:
                out, _ = proc.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn(b"syntheticNeverLog", out)
        self.assertNotIn(b"/cli/v1", out)
        self.assertFalse((self.root / "keylog").exists())
