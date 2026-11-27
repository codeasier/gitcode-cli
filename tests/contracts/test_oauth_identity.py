"""Offline contract for the internal OAuth identity read; no login or credential store."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

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
