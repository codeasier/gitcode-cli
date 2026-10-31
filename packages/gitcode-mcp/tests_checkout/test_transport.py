"""Installed-checkout producer probe; never selected against pygitcode 0.1.7."""

import httpx
import pytest

from gitcode_cli.transport import ResponseTooLargeError, read_response_bytes
from gitcode_mcp.api import GitCodeAPI


def test_installed_response_reader_can_bound_a_caller_owned_stream():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"four")

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        with client.stream("GET", "https://transport.invalid/resource") as response:
            with pytest.raises(ResponseTooLargeError):
                read_response_bytes(response, max_response_bytes=3)
        assert response.is_closed
    assert len(calls) == 1


def test_producer_does_not_replace_the_mcp_transport_or_auth_policy(monkeypatch):
    def unexpected_reader(*args, **kwargs):
        pytest.fail("The producer is not adopted by production clients in this slice")

    monkeypatch.setattr("gitcode_cli.transport.read_response_bytes", unexpected_reader)
    requests = []
    token = "synthetic-checkout-transport-token"

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"echo": token})

    with GitCodeAPI(token, transport=httpx.MockTransport(handler)) as api:
        assert api.get("/repos/team/project") == {"echo": "[REDACTED]"}
    assert len(requests) == 1
    request = requests[0]
    assert request.headers["Authorization"] == f"Bearer {token}"
    assert "private-token" not in request.headers
    assert "access_token" not in request.url.params
