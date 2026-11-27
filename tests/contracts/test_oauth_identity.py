"""Offline contract for the internal OAuth identity read; no login or credential store."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
import respx

from gitcode_cli import oauth_identity as identity
from gitcode_cli.errors import APIError, AuthError, GCError, NetworkError
from gitcode_cli.oauth_identity import OAuthIdentity, verify_oauth_identity

URL = "https://api.gitcode.com/api/v5/user"
TOKEN = "inert.fixture-token"
SUBJECT = "0fabcdef0123456789abcdef"
PROFILE = {"id": SUBJECT, "login": "Case.User"}


def test_fixed_bearer_request_and_minimal_identity(monkeypatch, caplog):
    monkeypatch.setenv("HTTPS_PROXY", "unsupported://inert.invalid:bad")
    monkeypatch.setenv("GC_TOKEN", "wrong-ambient-fixture")
    monkeypatch.setenv("SSL_CERT_FILE", "/does/not/exist/in/test")
    caplog.set_level(logging.DEBUG)

    def serve(req):
        assert req.method == "GET" and str(req.url) == URL and not req.content
        assert req.headers["Authorization"] == f"Bearer {TOKEN}"
        assert req.headers["Accept"] == "application/json"
        assert req.headers["Accept-Encoding"] == "identity"
        assert not {"cookie", "private-token", "proxy-authorization"}.intersection(req.headers)
        assert [name for name, value in req.headers.items() if TOKEN in value] == ["authorization"]
        return httpx.Response(
            200,
            json={**PROFILE, "email": "fixture@invalid.example", "ignored": TOKEN},
            headers={"set-cookie": "ambient=not-to-be-forwarded"},
        )

    with respx.mock(assert_all_mocked=True) as routes:
        routes.get(URL).mock(side_effect=serve)
        for _ in range(2):
            assert verify_oauth_identity(TOKEN) == OAuthIdentity(SUBJECT, "Case.User")
        assert len(routes.calls) == 2
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("change", [{"id": "00042"}, {"id": "Opaque-Subject_A"}, {"login": "Mixed_Case"}])
def test_exact_strings_no_numeric_or_case_normalization(change):
    profile = {**PROFILE, **change}
    with respx.mock() as routes:
        routes.get(URL).respond(200, json=profile)
        assert verify_oauth_identity(TOKEN) == OAuthIdentity(profile["id"], profile["login"])


@pytest.mark.parametrize(
    "token", [None, "", "too large" * 2000, "has space", "line\nbreak", "token\x7f", "测试", "foo,bar", "bad=pad=x"]
)
def test_invalid_credential_never_uses_anonymous_or_saved_identity(token, monkeypatch):
    monkeypatch.setenv("GC_TOKEN", TOKEN)
    with respx.mock() as routes, pytest.raises(GCError):
        verify_oauth_identity(token)
    assert not routes.calls


@pytest.mark.parametrize("status", [201, 204, 206, 302, 307, 401, 403, 429, 500])
def test_only_exact_200_no_body_location_retry_or_second_origin(status):
    with respx.mock() as routes:
        routes.get(URL).respond(status, headers={"Location": f"https://unrelated.invalid/{TOKEN}"}, json=PROFILE)
        with pytest.raises(APIError) as raised:
            verify_oauth_identity(TOKEN)
        assert len(routes.calls) == 1
    assert raised.value.status_code == status and TOKEN not in str(raised.value)


@pytest.mark.parametrize(
    "profile",
    [
        None,
        [],
        {},
        {"login": "Case.User"},
        {"id": SUBJECT},
        {**PROFILE, "id": True},
        {**PROFILE, "id": 123},
        {**PROFILE, "id": ""},
        {**PROFILE, "id": "id\x00"},
        {**PROFILE, "id": "one two"},
        {**PROFILE, "id": "a" * 513},
        {**PROFILE, "login": ""},
        {**PROFILE, "login": "a/b"},
        {**PROFILE, "login": None},
        {**PROFILE, "login": TOKEN},
        {**PROFILE, "id": f"contains-{TOKEN}"},
        {**PROFILE, "error": TOKEN},
    ],
)
def test_incomplete_contradictory_or_credential_echo_is_not_an_identity(profile):
    with respx.mock() as routes:
        routes.get(URL).respond(200, json=profile)
        with pytest.raises((AuthError, APIError)) as raised:
            verify_oauth_identity(TOKEN)
    assert TOKEN not in str(raised.value)


@pytest.mark.parametrize(
    "body, headers",
    [
        (b'{"login":"x", "id":"a", "id":"b"}', {}),
        (b'{"login":"x", "id":"a", "aux":{"k":0,"k":1}}', {}),
        (b'{"login":"x", "id":"a", "aux":NaN}', {}),
        (b'{"login":"x", "id":"a"}'.decode().encode("utf-16"), {}),
        (b'{"login":"x", "id":"a"}', {"Content-Type": "text/plain"}),
        (b'{"login":"x", "id":"a"}', {"Content-Type": "application/json; charset=utf-8,text/plain"}),
        (b"<not-json/>", {}),
        (b" " * (2 * 1024 * 1024 + 1), {}),
        (b"not-identity", {"Content-Encoding": "nonidentity"}),
    ],
)
def test_reject_ambiguous_or_unbounded_response(body, headers):
    with respx.mock() as routes:
        routes.get(URL).respond(200, content=body, headers={"Content-Type": "application/json", **headers})
        with pytest.raises(APIError):
            verify_oauth_identity(TOKEN)


def test_network_failure_is_sanitized_and_not_retried():
    with respx.mock() as routes:
        routes.get(URL).mock(side_effect=httpx.ConnectError(f"upstream trace {TOKEN}"))
        with pytest.raises(NetworkError) as raised:
            verify_oauth_identity(TOKEN)
        assert len(routes.calls) == 1
    assert TOKEN not in str(raised.value) and "upstream trace" not in str(raised.value)


@pytest.mark.parametrize(
    "addition",
    [b'"x":1e400', b'"x":-1e400', b'"x":' + b"1" * 130, b'"x":"\\ud800"', b'"\\udc00":[1]'],
)
def test_strict_json_in_ignored_profile_fields(addition):
    with respx.mock() as routes:
        routes.get(URL).respond(
            200,
            content=b'{"id":"ok","login":"fixture",' + addition + b"}",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(APIError):
            verify_oauth_identity(TOKEN)


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, *, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.close_count = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.close_count += 1


@pytest.mark.parametrize(
    "headers",
    [
        [("content-length", "65537")],
        [("content-length", "034")],
        [("content-length", "10"), ("content-length", "10")],
        [("content-length", "34"), ("transfer-encoding", "chunked")],
        [("content-type", "application/json")],
        [("x-note", "a" * 16_384)],
        [(f"x-{i}", "f") for i in range(64)],
    ],
)
def test_ambiguous_excessive_headers_rejected_before_body(headers, monkeypatch):
    body = Chunks([])
    response = httpx.Response(200, headers=[("content-type", "application/json"), *headers], stream=body)
    monkeypatch.setattr(identity, "_transport", lambda: httpx.MockTransport(lambda _: response))
    with pytest.raises(APIError):
        verify_oauth_identity(TOKEN)
    assert not response.is_stream_consumed and body.close_count == 1


@pytest.mark.parametrize("declared", [None, "30"])
def test_actual_stream_limit_or_length_mismatch(declared, monkeypatch, recwarn):
    chunks = [b" " * 32768, b" " * 32768, b"x"] if declared is None else [json.dumps(PROFILE).encode()]
    body = Chunks(chunks)
    headers = {"content-type": "application/json"}
    if declared:
        headers["content-length"] = declared
    monkeypatch.setattr(
        identity,
        "_transport",
        lambda: httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers=headers,
                stream=body,
            )
        ),
    )
    with pytest.raises(APIError):
        verify_oauth_identity(TOKEN)
    assert body.close_count == 1
    # In particular, 3.13 diagnoses partially consumed HTTPX async generators
    # when a private event loop closes without giving their finalizers a turn.
    assert not [w for w in recwarn if issubclass(w.category, RuntimeWarning)]


@pytest.mark.parametrize("during", ["headers", "body", "resolver"])
def test_one_call_deadline_closes_transport_and_does_not_join_resolver(monkeypatch, during):
    started = threading.Event()
    release = threading.Event()
    done = threading.Event()
    closed = []
    body = Chunks([b" "] * 100, delay=0.01)

    def blocking():
        started.set()
        try:
            release.wait(4)
        finally:
            done.set()

    class Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if during == "resolver":
                await asyncio.get_running_loop().run_in_executor(None, blocking)
            if during == "headers":
                await asyncio.sleep(4)
            return httpx.Response(200, headers={"content-type": "application/json"}, stream=body)

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(identity, "_TOTAL_SECONDS", 0.12)
    monkeypatch.setattr(identity, "_transport", Slow)
    before = time.monotonic()
    try:
        with pytest.raises(NetworkError):
            verify_oauth_identity(TOKEN)
        assert time.monotonic() - before < 2
        if during == "resolver":
            assert started.is_set() and not done.is_set()
    finally:
        release.set()
    assert closed == [True]
    assert body.close_count == int(during == "body")
    if during == "resolver":
        assert done.wait(2)


def test_sync_leaf_rejects_an_existing_event_loop_without_touching_transport(monkeypatch):
    monkeypatch.setattr(identity, "_transport", lambda: pytest.fail("network reached"))

    async def run():
        with pytest.raises(NetworkError):
            verify_oauth_identity(TOKEN)

    asyncio.run(run())


@pytest.mark.parametrize(
    "certificate_host,trust,ok",
    [
        ("api.gitcode.com", True, True),
        ("wrong.invalid", True, False),
        ("api.gitcode.com", False, False),
    ],
)
def test_real_loopback_tls_keeps_fixed_origin_and_ignores_ambient_secrets(
    tmp_path, monkeypatch, certificate_host, trust, ok
):
    # All DNS, TLS, HTTP, tokens and files in this test are private disposable fixtures.
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("generating the per-test certificate requires openssl")
    cert, key = tmp_path / "tls.crt", tmp_path / "tls.key"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={certificate_host}",
            "-addext",
            f"subjectAltName=DNS:{certificate_host}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
        check=True,
    )
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler
            requests.append((self.command, self.path, dict(self.headers)))
            body = json.dumps(PROFILE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    local = HTTPServer(("127.0.0.1", 0), Handler)
    original = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        assert host in {"api.gitcode.com", b"api.gitcode.com"} and port == local.server_port
        return original("127.0.0.1", local.server_port, *args, **kwargs)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    local.socket = context.wrap_socket(local.socket, server_side=True)
    thread = threading.Thread(target=local.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        # Keep scheme/host/SNI/path; only the test copy of the port is ephemeral.
        monkeypatch.setattr(identity, "_URL", URL.replace(".com/", f".com:{local.server_port}/"))
        monkeypatch.setattr(socket, "getaddrinfo", resolve)
        if trust:
            monkeypatch.setattr(identity.certifi, "where", lambda: str(cert))
        # SSL_CERT_FILE must not grant the trust=False case implicit trust.
        monkeypatch.setenv("SSL_CERT_FILE", str(cert))
        monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "ambient-keylog"))
        monkeypatch.setenv("HTTPS_PROXY", "http://bogus.invalid:55")
        if ok:
            assert verify_oauth_identity(TOKEN) == OAuthIdentity(SUBJECT, "Case.User")
        else:
            with pytest.raises(NetworkError):
                verify_oauth_identity(TOKEN)
        assert not (tmp_path / "ambient-keylog").exists()
    finally:
        local.shutdown()
        thread.join(2)
        local.server_close()
    if ok:
        [(method, target, headers)] = requests
        assert (method, target, headers["Host"]) == ("GET", "/api/v5/user", f"api.gitcode.com:{local.server_port}")
        assert headers["Authorization"] == f"Bearer {TOKEN}" and "Cookie" not in headers
    else:
        assert requests == []


def test_sync_interrupt_cancels_pending_io_and_closes_client(monkeypatch):
    closed = []

    def interrupt():
        raise KeyboardInterrupt

    class Interrupt(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            asyncio.get_running_loop().call_soon(interrupt)
            await asyncio.sleep(60)
            pytest.fail("interrupted request resumed")

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(identity, "_transport", Interrupt)
    with pytest.raises(KeyboardInterrupt):
        verify_oauth_identity(TOKEN)
    assert closed == [True]


def test_stalled_client_close_is_bounded_and_not_reported_as_verified(monkeypatch):
    touched = []

    class SlowClose(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(200, json=PROFILE)

        async def aclose(self):
            try:
                await asyncio.sleep(60)
            finally:
                touched.append(True)

    monkeypatch.setattr(identity, "_transport", SlowClose)
    monkeypatch.setattr(identity, "_CLOSE_SECONDS", 0.08)
    before = time.monotonic()
    with pytest.raises(NetworkError):
        verify_oauth_identity(TOKEN)
    assert touched == [True] and time.monotonic() - before < 2
