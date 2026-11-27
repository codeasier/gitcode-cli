"""Checkout-only CLI/broker contract on loopback TLS; neither live GitCode nor installed MCP.

Use a POSIX source checkout with its CLI and MCP dependencies, not MCP's published CLI pin:
    PYTHONPATH=src:packages/gitcode-mcp/src python -m unittest discover \
        -s packages/gitcode-mcp/tests_integration -p test_cli_oauth_coupled_tls.py -v
The browser/TTY, GitCode token/identity endpoints and native vault use synthetic boundaries.
"""

import asyncio
import html
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import unittest
from contextlib import asynccontextmanager, nullcontext
from functools import partial
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import uvicorn
from cryptography.fernet import Fernet
from gitcode_cli import oauth_credential_store as vault
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_broker_client import acquire_receipt
from gitcode_cli.oauth_identity import OAuthIdentity
from gitcode_cli.oauth_login import _TerminalSession, login_with_browser

from gitcode_mcp import cli_oauth_service as svc
from gitcode_mcp.oauth_upstream import AUTHORIZE_URL, TOKEN_URL, USER_URL

ACCOUNT = OAuthIdentity("test-subject", "test-user")
TOKEN = "synthetic-local-only"
CODE = "synthetic-auth-code"


class RawBody(httpx.AsyncByteStream):
    def __init__(self, payload):
        self.data = json.dumps(payload).encode()

    async def __aiter__(self):
        yield self.data


class MemoryVault:
    def __init__(self):
        self.records = {}
        self.operations = []

    def put(self, target, secret):
        self.operations.append("put")
        self.records[target] = secret

    def get(self, target):
        self.operations.append("get")
        return self.records[target]

    def delete(self, target):
        raise AssertionError("unexpected vault delete")


@asynccontextmanager
async def serve(root, listen, origin, upstream, api, pending):
    cert, key = root / "cert.pem", root / "key.pem"
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
    state = root / "state"
    state.mkdir(0o700)
    env = {
        "ENABLED": "1",
        "ORIGIN": origin,
        "APP_ID": "local-fixture",
        "STATE_DIR": str(state),
        "TLS_KEY_FILE": str(key),
        "TLS_CERT_FILE": str(cert),
    }
    for name, value in (
        ("APP_SECRET_FILE", b"fixture-secret"),
        ("ENCRYPTION_KEY_FILE", Fernet.generate_key()),
    ):
        path = root / name
        path.touch(mode=0o600)
        path.write_bytes(value)
        env[name] = str(path)
    cfg = svc.Settings.load({"GC_CLI_BROKER_" + k: v for k, v in env.items()})
    # Both the provider token exchange and the broker's /user go to the stub.
    with patch.object(svc, "_transport", side_effect=lambda: httpx.MockTransport(upstream)):
        app = svc.Service(cfg)

        async def observed(scope, receive, send):
            async def note(message):
                await send(message)
                if message["type"] == "http.response.start" and scope["path"] in (
                    svc.START,
                    svc.REDEEM,
                ):
                    result = (scope["path"], message["status"])
                    api.append(result)  # Never capture request fields, cookies or bodies.
                    if result == (svc.REDEEM, 202):
                        pending.set()

            await app(scope, receive, note)

        server = uvicorn.Server(
            uvicorn.Config(
                observed,
                interface="asgi3",
                http="h11",
                ws="none",
                lifespan="on",
                ssl_certfile=str(cert),
                ssl_keyfile=str(key),
                access_log=False,
                log_config=None,
                proxy_headers=False,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listen]))
        try:
            async with asyncio.timeout(8):
                while not server.started:
                    if task.done():
                        await task
                        raise AssertionError("broker stopped before accepting TLS")
                    await asyncio.sleep(0.01)
            verify = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            verify.load_verify_locations(cafile=str(cert))
            yield verify
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(task, timeout=8)
            finally:
                app.resources.close()


@unittest.skipUnless(os.name == "posix", "standalone loopback broker requires POSIX")
class CoupledLogin(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, decision):
        api, provider_calls, client_identities, opened = [], [], [], []
        pending, pairs = asyncio.Event(), asyncio.Queue()
        memory = MemoryVault()
        store = vault.OAuthCredentialStore(memory)

        async def upstream(req):
            endpoint = str(req.url.copy_with(query=None))
            provider_calls.append((req.method, endpoint))
            if (req.method, endpoint) == ("POST", TOKEN_URL):
                self.assertEqual(req.url.params["code"], CODE)
                data = {"access_token": TOKEN, "expires_in": 180}
            else:
                self.assertEqual((req.method, str(req.url)), ("GET", USER_URL))
                self.assertEqual(req.headers["Authorization"], "Bearer " + TOKEN)
                data = {"id": ACCOUNT.subject, "login": ACCOUNT.login}
            return httpx.Response(
                200, headers={"content-type": "application/json"}, stream=RawBody(data)
            )

        def client_identity(token):
            # Stand in for the CLI's own fixed-provider /user, not broker assertions.
            self.assertEqual(token, TOKEN)
            client_identities.append(ACCOUNT)
            return ACCOUNT

        with tempfile.TemporaryDirectory() as tmp, socket.socket() as listen:
            listen.bind(("127.0.0.1", 0))
            origin = f"https://127.0.0.1:{listen.getsockname()[1]}"
            async with (
                serve(Path(tmp), listen, origin, upstream, api, pending) as tls,
                httpx.AsyncClient(base_url=origin, verify=tls, trust_env=False) as browser,
            ):

                async def browser_flow():
                    pair = await pairs.get()
                    self.assertEqual(opened, [origin + svc.ENTRY])
                    self.assertEqual((await browser.get(svc.ENTRY)).status_code, 200)
                    # Force an actual pending exchange before consenting; do not fake the clock.
                    await pending.wait()
                    h = {"Origin": origin}
                    link = await browser.post(svc.ENTRY, headers=h, data={"pair": pair})
                    self.assertEqual(link.status_code, 200)
                    target = urlsplit(html.unescape(re.search(r'href="([^"]+)"', link.text)[1]))
                    self.assertEqual(target._replace(query="").geturl(), AUTHORIZE_URL)
                    params = parse_qs(target.query)
                    self.assertEqual(params["redirect_uri"], [origin + svc.CALLBACK])
                    # Never follow the external URL. The synthetic response stands in for its authorization code.
                    cb = await browser.get(
                        svc.CALLBACK, params={"state": params["state"][0], "code": CODE}
                    )
                    self.assertEqual((cb.status_code, cb.headers["location"]), (303, svc.CONSENT))
                    page = await browser.get(svc.CONSENT)
                    self.assertEqual(page.status_code, 200)
                    self.assertIn(ACCOUNT.login, page.text)
                    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
                    finish = await browser.post(
                        svc.CONSENT, headers=h, data={"csrf": csrf, "decision": decision}
                    )
                    self.assertEqual(
                        (finish.status_code, finish.headers["location"]), (303, svc.FINISHED)
                    )

                async def native():
                    # No production function or receipt is stubbed between terminal and broker.
                    return await login_with_browser(
                        origin,
                        _opener=opened.append,
                        _open_terminal=lambda: nullcontext(
                            _TerminalSession(lambda: None, pairs.put_nowait)
                        ),
                        _acquire=partial(
                            acquire_receipt,
                            _transport=httpx.AsyncHTTPTransport(
                                verify=tls, trust_env=False, retries=0
                            ),
                        ),
                        _store_factory=lambda: store,
                    )

                async def checked_login():
                    if decision == "allow":
                        self.assertEqual(await native(), ACCOUNT)
                    else:
                        with self.assertRaisesRegex(AuthError, "not confirmed"):
                            await native()

                with patch.object(vault, "verify_oauth_identity", side_effect=client_identity):
                    async with asyncio.timeout(22), asyncio.TaskGroup() as group:
                        group.create_task(browser_flow())
                        group.create_task(checked_login())

        final = 200 if decision == "allow" else 400
        self.assertEqual(api[0], (svc.START, 201))
        self.assertTrue(api[1:-1])  # permit additional pending polls on a busy CI runner
        self.assertTrue(all(row == (svc.REDEEM, 202) for row in api[1:-1]))
        self.assertEqual(api[-1], (svc.REDEEM, final))
        self.assertEqual(provider_calls, [("POST", TOKEN_URL), ("GET", USER_URL)])
        if decision == "allow":
            self.assertEqual(client_identities, [ACCOUNT])
            self.assertEqual(memory.operations, ["put", "get"])
            self.assertEqual(store.read(ACCOUNT).access_token, TOKEN)
        else:
            self.assertEqual(client_identities, [])
            self.assertEqual(memory.operations, [])
            self.assertEqual(memory.records, {})

    async def test_allow_commits_and_reads_back(self):
        await self.exercise("allow")

    async def test_deny_never_reaches_vault(self):
        await self.exercise("deny")
