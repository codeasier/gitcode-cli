import logging
import time
import traceback
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest

from gitcode_mcp.oauth_upstream import (
    MAX_RESPONSE_BYTES,
    GitCodeIdentity,
    GitCodeOAuthUpstream,
    OAuthUpstreamError,
)

CLIENT_ID = "gitcode-application-id"
CLIENT_SECRET = "private-gitcode-application-secret"
ACCESS = "private-upstream-access-token"
REFRESH = "private-upstream-refresh-token"
CODE = "private-upstream-authorization-code"
CALLBACK = "https://mcp.example.com/oauth/gitcode/callback"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def upstream(handler, **kwargs):
    return GitCodeOAuthUpstream(
        CLIENT_ID,
        CLIENT_SECRET,
        CALLBACK,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def tokens(**overrides):
    return {
        "access_token": ACCESS,
        "refresh_token": REFRESH,
        "expires_in": 3600,
        "scope": "all_user all_projects",
        **overrides,
    }


@pytest.mark.anyio
async def test_authorization_url_uses_fixed_host_and_explicit_consent():
    client = upstream(lambda _: pytest.fail("Authorization URL generation must not make requests"))
    try:
        url = urlsplit(client.authorization_url("opaque-state"))
        assert (url.scheme, url.netloc, url.path) == (
            "https",
            "gitcode.com",
            "/oauth/authorize",
        )
        assert parse_qs(url.query) == {
            "client_id": [CLIENT_ID],
            "redirect_uri": [CALLBACK],
            "response_type": ["code"],
            "state": ["opaque-state"],
            "prompt": ["consent"],
        }
        assert CLIENT_SECRET not in url.geturl()
    finally:
        await client.aclose()

    scoped = upstream(lambda _: None, scopes=("all_user", "all_projects"))
    try:
        assert parse_qs(urlsplit(scoped.authorization_url("state")).query)["scope"] == [
            "all_user all_projects"
        ]
    finally:
        await scoped.aclose()


@pytest.mark.anyio
async def test_code_exchange_uses_documented_query_and_multipart_secret():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=tokens())

    client = upstream(handler)
    before = time.time()
    try:
        result = await client.exchange_code(CODE)
    finally:
        await client.aclose()
    request = requests[0]
    assert request.method == "POST"
    assert request.url.host == "gitcode.com"
    assert request.url.path == "/oauth/token"
    assert dict(request.url.params) == {
        "grant_type": "authorization_code",
        "code": CODE,
        "client_id": CLIENT_ID,
    }
    assert request.headers["Content-Type"].startswith("multipart/form-data;")
    assert b'name="client_secret"' in request.content
    assert CLIENT_SECRET.encode() in request.content
    assert CLIENT_SECRET not in str(request.url)
    assert "Authorization" not in request.headers
    assert result.access_token == ACCESS
    assert result.refresh_token == REFRESH
    assert before + 3600 <= result.expires_at <= time.time() + 3600
    assert result.scope == "all_user all_projects"
    assert ACCESS not in repr(result) and REFRESH not in repr(result)


@pytest.mark.anyio
@pytest.mark.parametrize("rotated", [True, False])
async def test_refresh_rotates_or_preserves_refresh_token(rotated):
    requests = []
    response = tokens(access_token="new-access-token")
    if rotated:
        response["refresh_token"] = "new-refresh-token"
    else:
        del response["refresh_token"]

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response)

    client = upstream(handler)
    try:
        result = await client.refresh(REFRESH)
    finally:
        await client.aclose()
    request = requests[0]
    assert request.method == "POST"
    assert dict(request.url.params) == {"grant_type": "refresh_token", "refresh_token": REFRESH}
    assert request.content == b""
    assert CLIENT_SECRET not in str(request.url)
    assert result.access_token == "new-access-token"
    assert result.refresh_token == ("new-refresh-token" if rotated else REFRESH)


@pytest.mark.anyio
async def test_exchange_without_refresh_token_supports_non_refreshable_grant():
    payload = tokens()
    del payload["refresh_token"]
    client = upstream(lambda _: httpx.Response(200, json=payload))
    try:
        assert (await client.exchange_code(CODE)).refresh_token == ""
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "identity"),
    [
        ({"id": 42, "login": "codeasier"}, GitCodeIdentity("42", "codeasier")),
        ({"id": "user-42", "login": "codeasier"}, GitCodeIdentity("user-42", "codeasier")),
        ({"id": 42}, GitCodeIdentity("42", "42")),
        ({"id": "42", "login": None}, GitCodeIdentity("42", "42")),
    ],
)
async def test_user_identity_uses_bearer_header_and_stable_subject(payload, identity):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = upstream(handler)
    try:
        assert await client.user(ACCESS) == identity
    finally:
        await client.aclose()
    request = requests[0]
    assert str(request.url) == "https://api.gitcode.com/api/v5/user"
    assert request.headers["Authorization"] == f"Bearer {ACCESS}"
    assert ACCESS not in str(request.url)


@pytest.mark.anyio
async def test_response_cookies_do_not_cross_user_requests():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json=tokens(),
                headers={"Set-Cookie": "session=first-user; Domain=.gitcode.com; Path=/; Secure"},
            )
        return httpx.Response(200, json={"id": "second-user"})

    client = upstream(handler)
    try:
        await client.exchange_code(CODE)
        assert (await client.user("second-user-access-token")).subject == "second-user"
    finally:
        await client.aclose()
    assert "Cookie" not in requests[1].headers
    assert requests[1].headers["Authorization"] == "Bearer second-user-access-token"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"id": True},
        {"id": None},
        {},
        {"id": ""},
        {"id": 1.2},
        {"id": []},
        {"id": "a\nb"},
        {"id": 42, "login": True},
    ],
)
async def test_user_rejects_ambiguous_or_invalid_identities(payload):
    client = upstream(lambda _: httpx.Response(200, json=payload))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.user(ACCESS)
    finally:
        await client.aclose()
    assert raised.value.code == "invalid_response"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"access_token": ""},
        {"access_token": "contains space"},
        {"access_token": "control\x7f"},
        {"access_token": "control\x00"},
        {"access_token": 1},
        {"refresh_token": "newline\n"},
        {"refresh_token": None},
        {"expires_in": None},
        {"expires_in": False},
        {"expires_in": 0},
        {"expires_in": -1},
        {"expires_in": "3600"},
        {"expires_in": 10**1000},
        {"scope": ["all_user"]},
    ],
)
async def test_token_response_values_are_validated(overrides):
    client = upstream(lambda _: httpx.Response(200, json=tokens(**overrides)))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.exchange_code(CODE)
    finally:
        await client.aclose()
    assert raised.value.code == "invalid_response"


@pytest.mark.anyio
@pytest.mark.parametrize("duration", ["NaN", "Infinity", "-Infinity"])
async def test_nonfinite_expiry_is_rejected(duration):
    body = '{"access_token":"valid","expires_in":' + duration + "}"
    client = upstream(lambda _: httpx.Response(200, text=body))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.exchange_code(CODE)
    finally:
        await client.aclose()
    assert raised.value.code == "invalid_response"


@pytest.mark.anyio
async def test_response_limit_stops_reading_without_truncating_success():
    chunks_read = []

    class LargeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(100):
                chunks_read.append(index)
                yield b"x" * 8192

    client = upstream(lambda _: httpx.Response(200, stream=LargeStream()))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.exchange_code(CODE)
    finally:
        await client.aclose()
    assert raised.value.code == "response_too_large"
    assert len(chunks_read) <= MAX_RESPONSE_BYTES // 8192 + 1


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["exchange_code", "refresh", "user"])
async def test_redirects_are_never_followed(operation):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": f"https://attacker.example/{CLIENT_SECRET}"}
        )

    client = upstream(handler)
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await getattr(client, operation)(CODE)
    finally:
        await client.aclose()
    assert len(requests) == 1
    assert raised.value.code == "upstream_redirect"
    assert CLIENT_SECRET not in str(raised.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (400, {"error": "invalid_grant", "error_description": REFRESH}, "invalid_grant"),
        (401, {"error": "invalid_client", "error_description": CLIENT_SECRET}, "invalid_client"),
        (500, {"error": CLIENT_SECRET}, "upstream_error"),
        (400, {"error": {"secret": CLIENT_SECRET}}, "upstream_error"),
        (200, {"error": [CLIENT_SECRET]}, "upstream_error"),
        (200, [CLIENT_SECRET], "invalid_response"),
    ],
)
async def test_upstream_error_bodies_are_not_exposed(status, body, error):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=body)

    client = upstream(handler)
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.refresh(REFRESH)
    finally:
        await client.aclose()
    assert raised.value.code == error
    assert len(requests) == 1
    assert CLIENT_SECRET not in str(raised.value)
    assert REFRESH not in str(raised.value)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403])
async def test_user_unauthorized_is_invalid_grant_even_without_json(status):
    client = upstream(lambda _: httpx.Response(status, text=ACCESS))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.user(ACCESS)
    finally:
        await client.aclose()
    assert raised.value.code == "invalid_grant"
    assert ACCESS not in str(raised.value)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [200, 500])
async def test_malformed_json_errors_are_safe(status):
    client = upstream(lambda _: httpx.Response(status, text=CLIENT_SECRET))
    try:
        with pytest.raises(OAuthUpstreamError) as raised:
            await client.exchange_code(CODE)
    finally:
        await client.aclose()
    assert raised.value.code == ("invalid_response" if status == 200 else "upstream_error")
    assert CLIENT_SECRET not in "".join(traceback.format_exception(raised.value))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception_type", "error"),
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network_error")],
)
async def test_http_exceptions_are_sanitized_without_retries(exception_type, error, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        logging.getLogger("httpcore.connection").debug("failed request: %s", request.url)
        raise exception_type(f"upstream leaked {CLIENT_SECRET} in {request.url}", request=request)

    client = upstream(handler)
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(OAuthUpstreamError) as raised:
            await client.refresh(REFRESH)
    finally:
        await client.aclose()
    assert raised.value.code == error
    assert len(requests) == 1
    visible = caplog.text + "".join(traceback.format_exception(raised.value))
    assert CLIENT_SECRET not in visible
    assert REFRESH not in visible


@pytest.mark.anyio
async def test_transport_logs_hide_oauth_secrets_but_preserve_other_concurrent_client(caplog):
    entered = anyio.Event()
    release = anyio.Event()

    async def handler(request):
        logging.getLogger("httpcore.http11").debug("upstream echoed %s", ACCESS)
        entered.set()
        await release.wait()
        return httpx.Response(200, json=tokens())

    client = upstream(handler)
    try:
        with caplog.at_level(logging.DEBUG):
            async with anyio.create_task_group() as group:
                group.start_soon(client.refresh, REFRESH)
                await entered.wait()
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _: httpx.Response(200)), trust_env=False
                ) as other:
                    await other.get("https://visible.example/other-client")
                release.set()
            logging.getLogger("httpcore.connection").debug("normal-client-debug-still-visible")
    finally:
        await client.aclose()
    assert REFRESH not in caplog.text
    assert ACCESS not in caplog.text
    assert "https://visible.example/other-client" in caplog.text
    assert "normal-client-debug-still-visible" in caplog.text


@pytest.mark.anyio
async def test_invalid_request_values_fail_before_network():
    client = upstream(lambda _: pytest.fail("Invalid credentials must not reach the network"))
    try:
        for method in (client.exchange_code, client.refresh, client.user):
            for value in ("", "a b", "a\r\nb", "a\x00b"):
                with pytest.raises(OAuthUpstreamError):
                    await method(value)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"client_secret": ""},
        {"client_id": "bad id"},
        {"client_secret": "bad\nsecret"},
        {"callback_url": "http://public.example/callback"},
        {"callback_url": "https://user:secret@mcp.example/callback"},
        {"callback_url": "https://mcp.example/callback?secret=value"},
        {"timeout": 0},
        {"timeout": False},
        {"timeout": float("nan")},
        {"timeout": 10**1000},
    ],
)
def test_invalid_configuration_has_safe_errors(kwargs):
    values = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "callback_url": CALLBACK}
    values.update(kwargs)
    with pytest.raises(OAuthUpstreamError) as raised:
        GitCodeOAuthUpstream(**values)
    assert raised.value.code == "invalid_configuration"
    assert CLIENT_SECRET not in str(raised.value)
