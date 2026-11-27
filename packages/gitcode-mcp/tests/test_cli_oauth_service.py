"""Socket-free assembly contracts using files and synthetic in-process transports."""

import asyncio
import base64
import hashlib
import html
import json
import os
import re
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.fernet import Fernet

from gitcode_mcp import cli_oauth_service as svc
from gitcode_mcp.oauth_upstream import TOKEN_URL, USER_URL, OAuthUpstreamError

TOKEN = "synthetic-oauth.receipt+/="


class Body(httpx.AsyncByteStream):
    def __init__(self, raw):
        self.raw = raw

    async def __aiter__(self):
        yield self.raw


def profile(raw, code=200, **headers):
    return httpx.Response(
        code, stream=Body(raw), headers={"content-type": "application/json", **headers}
    )


@unittest.skipUnless(os.name == "posix", "standalone direct-TLS pilot is POSIX only")
class ServiceTest(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(root)
        self.folder = self.root / "state"
        self.folder.mkdir(0o700)
        self.env = {
            "GC_CLI_BROKER_" + k: v
            for k, v in {
                "ENABLED": "1",
                "ORIGIN": "https://127.0.0.1:48572",
                "APP_ID": "fixture-app",
                "STATE_DIR": str(self.folder),
            }.items()
        }
        for name, value in (
            ("TLS_CERT_FILE", b"fake cert"),
            ("TLS_KEY_FILE", b"fake key"),
            ("APP_SECRET_FILE", b"fixture-app-private"),
            ("ENCRYPTION_KEY_FILE", Fernet.generate_key()),
        ):
            f = self.root / name
            f.write_bytes(value)
            f.chmod(0o600)
            self.env["GC_CLI_BROKER_" + name] = str(f)

    def settings(self):
        return svc.Settings.load(self.env)

    def test_opt_in_and_origin(self):
        self.assertNotIn("fixture-app-private", repr(self.settings()))
        for env in (
            {},
            {"GITCODE_MCP_OAUTH_ENABLED": "1"},
            self.env | {"GC_CLI_BROKER_ENABLED": "0"},
            self.env | {"GC_CLI_BROKER_CALLBACK": "bad"},
            *(
                self.env | {"GC_CLI_BROKER_ORIGIN": x}
                for x in (
                    "https://0.0.0.0:4888",
                    "https://example.test",
                    "http://127.0.0.1:4888",
                    "https://127.0.0.1:1",
                    "https://127.0.0.1:4888/mcp",
                    "https://127.0.0.1:4888?x",
                    "https://127.0.0.1:84888",
                )
            ),
        ):
            with self.subTest(envkeys=env.keys()), self.assertRaises(svc.ServiceError):
                svc.Settings.load(env)
        self.assertEqual(
            self.settings(), svc.Settings.load(self.env | {"GITCODE_MCP_OAUTH_ENABLED": "1"})
        )

    def test_private_dedicated_state(self):
        s = self.settings()
        key = self.root / "APP_SECRET_FILE"
        key.chmod(0o640)
        with self.assertRaises(svc.ServiceError):
            self.settings()
        key.chmod(0o600)
        foreign = self.folder / "mcp.sqlite"
        foreign.write_bytes(b"non-CLI DB")
        with self.assertRaises(svc.ServiceError):
            svc.Service(s)
        self.assertEqual(list(self.folder.iterdir()), [foreign])
        foreign.unlink()
        alias = self.root / "alias"
        os.symlink(key, alias)
        with self.assertRaises(svc.ServiceError):
            svc.Settings.load(self.env | {"GC_CLI_BROKER_APP_SECRET_FILE": str(alias)})
        with svc._acquire(s), self.assertRaises(BlockingIOError):
            svc._acquire(s)
        with self.assertRaises(svc.ServiceError):
            svc._acquire(svc.Settings.load(self.env | {"GC_CLI_BROKER_APP_ID": "other"}))
        with svc._acquire(s):
            pass
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)

    def test_strict_fixed_identity_and_total_timeout(self):
        subjects = [
            b'{"id":42,"login":"user"}',
            b'{"id":"42"}',
            b'{"id":"a","login":".."}',
            b'{"id":"a","login":"ok","error":false}',
            b'{"id":"1","id":"2","login":"ok"}',
            b'{"id":"a","login":"ok","x":Infinity}',
            b'{"id":"hello world","login":"ok"}',
            json.dumps({"id": TOKEN, "login": "ok"}).encode(),
            json.dumps({"id": "access_token=x", "login": "ok"}).encode(),
        ]

        async def run():
            for resp in [
                *(profile(s) for s in subjects),
                profile(b"x" * 65537),
                profile(b"{}", 302, location="https://other.test"),
                profile(b"{}", **{"content-encoding": "gzip"}),
                profile(b"{}", **{"content-length": "8"}),
                profile(b"{}", **{"content-type": "text/html"}),
            ]:

                async def read(_req, response=resp):
                    return response

                with self.assertRaises(OAuthUpstreamError):
                    await svc._identity(TOKEN, httpx.MockTransport(read))

            async def slow(_):
                await asyncio.sleep(10)

            with patch.object(svc, "_ID_TIMEOUT", 0.02), self.assertRaises(OAuthUpstreamError):
                await svc._identity(TOKEN, httpx.MockTransport(slow))

        asyncio.run(run())

    def test_end_to_end_with_synthetic_provider(self):
        s = self.settings()
        calls = []

        async def upstream(request):
            calls.append((request.method, str(request.url.copy_with(query=None))))
            if calls[-1] == ("POST", TOKEN_URL):
                self.assertNotIn("Authorization", request.headers)
                return profile(json.dumps({"access_token": TOKEN, "expires_in": 180}).encode())
            self.assertEqual(calls[-1], ("GET", USER_URL))
            self.assertEqual(request.headers["Authorization"], "Bearer " + TOKEN)
            self.assertEqual(str(request.url), USER_URL)
            self.assertNotIn("Cookie", request.headers)
            self.assertEqual(request.headers["Accept-Encoding"], "identity")
            return profile(b'{"id":"f0abc91","login":"synthetic-user"}')

        async def run():
            with patch.object(svc, "_transport", side_effect=lambda: httpx.MockTransport(upstream)):
                app = svc.Service(s)
                try:
                    async with (
                        httpx.AsyncClient(
                            base_url=s.origin, transport=httpx.ASGITransport(app=app)
                        ) as cli,
                        httpx.AsyncClient(
                            base_url=s.origin, transport=httpx.ASGITransport(app=app)
                        ) as browser,
                    ):
                        proof = secrets.token_urlsafe(32)
                        ch = (
                            base64.urlsafe_b64encode(hashlib.sha256(proof.encode()).digest())
                            .decode()
                            .rstrip("=")
                        )
                        p = await cli.post(svc.START, json={"challenge": ch})
                        self.assertEqual(p.status_code, 201)
                        d = p.json()
                        self.assertEqual(d["browser_url"], s.origin + svc.ENTRY)
                        h = {"Origin": s.origin}
                        r = await browser.post(svc.ENTRY, headers=h, data={"pair": d["pairing"]})
                        u = urlsplit(html.unescape(re.search(r'href="([^"]+)"', r.text)[1]))
                        params = parse_qs(u.query)
                        self.assertEqual(
                            (u.scheme, u.netloc, u.path),
                            ("https", "gitcode.com", "/oauth/authorize"),
                        )
                        self.assertEqual(params["redirect_uri"], [s.origin + svc.CALLBACK])
                        self.assertNotIn("scope", params)
                        r = await browser.get(
                            svc.CALLBACK,
                            params={"code": "syntheticCode", "state": params["state"][0]},
                        )
                        self.assertEqual(r.headers.get("location"), svc.CONSENT)
                        page = await browser.get(svc.CONSENT)
                        self.assertIn("synthetic-user", page.text)
                        self.assertNotIn(TOKEN, page.text)
                        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
                        r = await browser.post(
                            svc.CONSENT, headers=h, data={"csrf": csrf, "decision": "allow"}
                        )
                        self.assertEqual(r.headers["location"], svc.FINISHED)
                        receipt = {"selector": d["selector"], "verifier": proof}
                        ok = await cli.post(svc.REDEEM, json=receipt)
                        self.assertEqual(ok.status_code, 200)
                        self.assertEqual(ok.json()["subject"], "f0abc91")
                        self.assertEqual(ok.json()["access_token"], TOKEN)
                        self.assertNotEqual(
                            (await cli.post(svc.REDEEM, json=receipt)).status_code, 200
                        )
                        self.assertEqual((await cli.get("/mcp")).status_code, 404)
                    self.assertEqual(calls, [("POST", TOKEN_URL), ("GET", USER_URL)])
                finally:
                    await app.broker.aclose()
                    app.resources.close()

        asyncio.run(run())
