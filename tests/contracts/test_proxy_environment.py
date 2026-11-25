"""Proxy environment controls with no network or ambient credentials."""

from __future__ import annotations

import json

import httpcore
import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.client import GitCodeClient


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_config_dir):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "GC_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("no_proxy", "expected_route"),
    [("localhost,::1", "proxy"), ("api.gitcode.com,localhost,::1", "direct")],
)
def test_proxy_and_no_proxy_still_select_the_expected_transport(monkeypatch, no_proxy, expected_route):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("NO_PROXY", no_proxy)
    routes = []

    def record(route):
        def handle(_pool, request):
            assert request.url.host == b"api.gitcode.com"
            routes.append(route)
            return httpcore.Response(200, content=b'{"id":1}')

        return handle

    monkeypatch.setattr(httpcore.HTTPProxy, "handle_request", record("proxy"))
    monkeypatch.setattr(httpcore.ConnectionPool, "handle_request", record("direct"))

    client = GitCodeClient("")
    try:
        assert client.get("/repos/owner/repo/issues/1") == {"id": 1}
        assert routes == [expected_route]
    finally:
        client.close()


def test_fixed_origin_comments_client_still_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "[::1]")
    requests = []

    def handle(_transport, request):
        assert request.method == "GET"
        assert request.url.host == "api.gitcode.com"
        assert "access_token" not in request.url.params
        requests.append(request.url.path)
        payload = (
            []
            if request.url.path.endswith("/comments")
            else {"id": 1, "number": 1129, "html_url": "https://gitcode.com/openeuler/community/issues/1129"}
        )
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    result = CliRunner().invoke(
        main, ["issue", "view", "1129", "-R", "openeuler/community", "--json", "number,comments"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"number": 1129, "comments": []}
    assert requests == [
        "/api/v5/repos/openeuler/community/issues/1129",
        "/api/v5/repos/openeuler/community/issues/1129/comments",
    ]


def test_unrelated_default_client_value_error_is_not_reclassified(monkeypatch):
    failure = ValueError("unrelated TLS configuration error")

    def reject_client(**_kwargs):
        raise failure

    monkeypatch.setattr(httpx, "Client", reject_client)
    with pytest.raises(ValueError) as caught:
        GitCodeClient("")
    assert caught.value is failure
