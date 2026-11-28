"""Origin-scoped, explicit CA trust on the real native broker transport; no upstream OAuth or storage."""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import ssl
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from gitcode_cli import oauth_broker_client as client
from gitcode_cli.errors import AuthError


def _openssl(directory, *args):
    program = shutil.which("openssl")
    if program is None:
        pytest.skip("generating disposable loopback certificates requires openssl")
    subprocess.run([program, *args], cwd=directory, capture_output=True, check=True, timeout=20)


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    root = tmp_path_factory.mktemp("broker-pki")
    for name in ("chosen", "unrelated"):
        _openssl(
            root,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={name}",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-keyout",
            f"{name}.key",
            "-out",
            f"{name}.pem",
        )
    _openssl(
        root,
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=fixture",
        "-keyout",
        "server.key",
        "-out",
        "server.csr",
    )
    for cert, san in (("valid", "IP:127.0.0.1"), ("wrong", "DNS:other.invalid")):
        (root / "server.ext").write_text(
            f"basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nsubjectAltName={san}\n", encoding="ascii"
        )
        _openssl(
            root,
            "x509",
            "-req",
            "-in",
            "server.csr",
            "-CA",
            "chosen.pem",
            "-CAkey",
            "chosen.key",
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            "server.ext",
            "-out",
            f"{cert}.pem",
        )
    return root


@contextmanager
def tls_broker(pki, server_cert, redirect):
    calls, handshakes = [], []
    selector, proof, token = (secrets.token_urlsafe(32) for _ in range(3))

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib handler
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            calls.append((self.path, set(body), {k.lower() for k in self.headers}))
            if redirect:
                self.send_response(307)
                self.send_header("Location", origin + "/not-a-broker-route")
                self.end_headers()
                return
            if self.path == "/cli/v1/start":
                status = 201
                reply = {
                    "selector": selector,
                    "pairing": selector + "." + proof,
                    "browser_url": origin + "/cli/v1/browser",
                }
            else:
                status = 200
                reply = {
                    "status": "authorized",
                    "access_token": token,
                    "subject": "123",
                    "login": "fixture",
                    "expires_at": int(time.time()) + 120,
                }
            raw = json.dumps(reply).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        origin = f"https://127.0.0.1:{server.server_port}"
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(pki / f"{server_cert}.pem", pki / "server.key")
        context.set_servername_callback(lambda *_: handshakes.append(True))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        worker.start()
        try:
            yield origin, calls, handshakes, (origin + "/cli/v1/browser", selector + "." + proof), token
        finally:
            server.shutdown()
            worker.join(3)


@pytest.mark.parametrize(
    "choice,server_cert,redirect,expected_count",
    [
        ("chosen", "valid", False, 2),
        (None, "valid", False, 0),
        ("unrelated", "valid", False, 0),
        ("chosen", "wrong", False, 0),
        ("chosen", "valid", True, 1),
    ],
)
def test_native_broker_tls(pki, tmp_path, monkeypatch, choice, server_cert, redirect, expected_count):
    shown = []
    keylog = tmp_path / "unused-keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog))
    monkeypatch.setenv("SSL_CERT_FILE", str(pki / "chosen.pem"))
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("GC_TOKEN", "unrelated-ambient-token")

    async def present(url, pair):
        shown.append((url, pair))

    with tls_broker(pki, server_cert, redirect) as (origin, calls, handshakes, expected_pair, token):
        # No test transport and no patch to certifi, the SSL context factory, resolver, or HTTP stack.
        kwargs = {} if choice is None else {"trust": client.BrokerTrust(origin, (pki / f"{choice}.pem").read_text())}
        if choice is not None and any(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).cert_store_stats().values()):
            # A platform-preseeded store cannot offer private-CA-only trust. Fail before the first POST.
            with pytest.raises(AuthError, match="Invalid explicit OAuth broker trust configuration"):
                asyncio.run(client.acquire_receipt(origin, present, **kwargs))
            assert calls == [] and handshakes == [] and shown == [] and not keylog.exists()
            return
        if expected_count == 2:
            got = asyncio.run(client.acquire_receipt(origin, present, **kwargs))
            assert got.access_token == token and got.login == "fixture" and shown == [expected_pair]
        else:
            with pytest.raises(AuthError) as exc:
                asyncio.run(client.acquire_receipt(origin, present, **kwargs))
            assert not shown and token not in str(exc.value) and str(pki) not in str(exc.value)
        assert len(handshakes) == max(1, expected_count)  # HTTP/1.0 fixture closes after each response; no retry.
        assert len(calls) == expected_count
        assert [(path, keys) for path, keys, _ in calls] == [
            ("/cli/v1/start", {"challenge"}),
            ("/cli/v1/redeem", {"selector", "verifier"}),
        ][:expected_count]
        assert all(not names & {"authorization", "proxy-authorization", "cookie", "referer"} for _, _, names in calls)
        assert not keylog.exists()


@pytest.mark.parametrize(
    "kind", ["origin", "malformed", "path", "oversize", "bundle", "leaf", "key", "der-tail", "untyped", "seam"]
)
def test_bad_trust_never_constructs_transport_or_presents(pki, monkeypatch, kind):
    origin = "https://broker.invalid"
    cert = (pki / "chosen.pem").read_text()
    values = {
        "malformed": "-----BEGIN CERTIFICATE-----\nAA==\n-----END CERTIFICATE-----\n",
        "path": str(pki / "chosen.pem"),
        "oversize": cert + "\n" * 16_385,
        "bundle": cert + (pki / "unrelated.pem").read_text(),
        "leaf": (pki / "valid.pem").read_text(),
        "key": (pki / "chosen.key").read_text(),
        "der-tail": ssl.DER_cert_to_PEM_cert(ssl.PEM_cert_to_DER_cert(cert) + b"trailing-fixture"),
    }
    trust = client.BrokerTrust(origin if kind != "origin" else origin + ":8443", values.get(kind, cert))
    selected = {"origin": origin, "ca_pem": cert} if kind == "untyped" else trust
    assert cert not in repr(trust)
    contacts = []

    def unexpected(*args, **kwargs):
        contacts.append(True)
        pytest.fail("permitted network or UI for untrusted configuration")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", unexpected)
    transport = httpx.MockTransport(unexpected) if kind == "seam" else None
    with pytest.raises(AuthError) as exc:
        asyncio.run(client.acquire_receipt(origin, unexpected, trust=selected, _transport=transport))
    assert not contacts and cert not in str(exc.value) and str(pki) not in str(exc.value)
