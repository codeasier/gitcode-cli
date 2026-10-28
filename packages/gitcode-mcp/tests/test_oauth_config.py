import pytest
from cryptography.fernet import Fernet

from gitcode_mcp.config import ConfigurationError, Settings


@pytest.fixture
def oauth_env(tmp_path):
    return {
        "GITCODE_MCP_AUTH_MODE": "oauth",
        "GITCODE_MCP_PUBLIC_URL": "https://gitcode-mcp.example.com/",
        "GITCODE_OAUTH_CLIENT_ID": "gitcode-application-id",
        "GITCODE_OAUTH_CLIENT_SECRET": "private-gitcode-application-secret",
        "GITCODE_MCP_OAUTH_CLIENT_ID": "chatgpt-client-id",
        "GITCODE_MCP_OAUTH_CLIENT_SECRET": "private-chatgpt-client-secret-value-12345",
        "GITCODE_MCP_OAUTH_REDIRECT_URIS": "https://chatgpt.com/connector/oauth/exact-callback-id",
        "GITCODE_MCP_OAUTH_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "GITCODE_MCP_OAUTH_DATABASE": str(tmp_path / "oauth.sqlite3"),
    }


def test_oauth_configuration_has_separate_credentials_and_canonical_public_endpoints(oauth_env):
    oauth_env.update(
        {
            "GITCODE_MCP_READ_ONLY": "true",
            "GITCODE_MCP_ALLOWED_REPOS": "Ascend/msinsight",
            "GITCODE_OAUTH_SCOPES": "all_user all_projects",
            "GITCODE_MCP_OAUTH_ALLOWED_USER_IDS": "42,507f1f77bcf86cd799439011,user-uuid",
        }
    )
    settings = Settings.from_env(oauth_env)
    oauth = settings.oauth
    assert oauth is not None
    assert oauth.public_url == "https://gitcode-mcp.example.com"
    assert oauth.resource_url == "https://gitcode-mcp.example.com/mcp"
    assert oauth.callback_url == "https://gitcode-mcp.example.com/oauth/gitcode/callback"
    assert oauth.gitcode_client_id == oauth_env["GITCODE_OAUTH_CLIENT_ID"]
    assert oauth.client_id == oauth_env["GITCODE_MCP_OAUTH_CLIENT_ID"]
    assert oauth.redirect_uris == ("https://chatgpt.com/connector/oauth/exact-callback-id",)
    assert oauth.gitcode_scopes == ("all_user", "all_projects")
    assert oauth.allowed_user_ids == ("42", "507f1f77bcf86cd799439011", "user-uuid")
    assert settings.read_only
    assert settings.allowed_repositories == ("Ascend/msinsight",)
    assert settings.token == settings.http_token == ""
    for key in (
        "GITCODE_OAUTH_CLIENT_SECRET",
        "GITCODE_MCP_OAUTH_CLIENT_SECRET",
        "GITCODE_MCP_OAUTH_ENCRYPTION_KEY",
    ):
        assert oauth_env[key] not in repr(settings)
        assert oauth_env[key] not in repr(oauth)


def test_discovery_can_start_before_chatgpt_callback_is_known(oauth_env):
    del oauth_env["GITCODE_MCP_OAUTH_REDIRECT_URIS"]
    settings = Settings.from_env(oauth_env)
    assert settings.oauth is not None
    assert settings.oauth.redirect_uris == ()
    assert settings.oauth.resource_url.endswith("/mcp")


@pytest.mark.parametrize("value", ["", " , "])
def test_explicit_empty_redirect_configuration_remains_closed_to_all_clients(oauth_env, value):
    settings = Settings.from_env({**oauth_env, "GITCODE_MCP_OAUTH_REDIRECT_URIS": value})
    assert settings.oauth.redirect_uris == ()


@pytest.mark.parametrize(
    "value",
    [
        "http://gitcode-mcp.example.com",
        "https://gitcode-mcp.example.com/mcp",
        "https://gitcode-mcp.example.com?key=private-query",
        "https://gitcode-mcp.example.com#fragment",
        "https://user:private-password@gitcode-mcp.example.com",
        "https://@gitcode-mcp.example.com",
        "https://*.example.com",
        "https://gitcode-mcp.example.com:0",
        "https://gitcode-mcp.example.com:65536",
        "https://gitcode-mcp.example.com:invalid",
        "https://gitcode-mcp.example.com\x00",
        "https://gitcode-mcp.example.com\x7f",
    ],
)
def test_public_url_must_be_an_unambiguous_https_origin(oauth_env, value):
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env({**oauth_env, "GITCODE_MCP_PUBLIC_URL": value})
    assert value not in str(raised.value)


@pytest.mark.parametrize(
    "value",
    [
        "http://chatgpt.com/connector/oauth/callback-id",
        "https://chatgpt.com/connector/oauth/*",
        "https://*.chatgpt.com/callback",
        "https://chatgpt.com/connector/oauth/callback-id#fragment",
        "https://private-user@chatgpt.com/callback",
        "https://chatgpt.com\\@other.example/callback",
        "https://chatgpt.com/callback\x7f",
    ],
)
def test_redirect_allowlist_requires_exact_https_urls(oauth_env, value):
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env({**oauth_env, "GITCODE_MCP_OAUTH_REDIRECT_URIS": value})
    assert value not in str(raised.value)


def test_multiple_exact_redirects_are_preserved(oauth_env):
    redirects = (
        "https://chatgpt.com/connector/oauth/first-id",
        "https://chatgpt.com/connector/oauth/second-id",
    )
    settings = Settings.from_env(
        {**oauth_env, "GITCODE_MCP_OAUTH_REDIRECT_URIS": ", ".join(redirects)}
    )
    assert settings.oauth.redirect_uris == redirects


@pytest.mark.parametrize("name", ["GITCODE_TOKEN", "GC_TOKEN", "GITCODE_MCP_HTTP_TOKEN"])
def test_oauth_cannot_fall_back_to_shared_pat_or_static_bearer(oauth_env, name):
    value = "private-unrelated-shared-credential-12345"
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env({**oauth_env, name: value})
    assert value not in str(raised.value)


@pytest.mark.parametrize(
    "field",
    [
        "GITCODE_MCP_PUBLIC_URL",
        "GITCODE_OAUTH_CLIENT_ID",
        "GITCODE_OAUTH_CLIENT_SECRET",
        "GITCODE_MCP_OAUTH_CLIENT_ID",
        "GITCODE_MCP_OAUTH_CLIENT_SECRET",
        "GITCODE_MCP_OAUTH_ENCRYPTION_KEY",
    ],
)
def test_oauth_configuration_requires_material_credentials(oauth_env, field):
    del oauth_env[field]
    with pytest.raises(ConfigurationError):
        Settings.from_env(oauth_env)


@pytest.mark.parametrize("value", ["not-a-fernet-key", "A" * 32, "é" * 44, "A\n" * 22])
def test_storage_key_must_be_a_real_fernet_key_without_exposing_value(oauth_env, value):
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env({**oauth_env, "GITCODE_MCP_OAUTH_ENCRYPTION_KEY": value})
    assert value not in str(raised.value)


@pytest.mark.parametrize(
    "value", ["oauth.sqlite3", "../oauth.sqlite3", "~/oauth.sqlite3", "", "/tmp/oauth\x00.sqlite3"]
)
def test_database_requires_absolute_persistent_file_path(oauth_env, value):
    with pytest.raises(ConfigurationError):
        Settings.from_env({**oauth_env, "GITCODE_MCP_OAUTH_DATABASE": value})


@pytest.mark.parametrize(
    ("target", "source"),
    [
        ("GITCODE_OAUTH_CLIENT_SECRET", "GITCODE_MCP_OAUTH_CLIENT_SECRET"),
        ("GITCODE_MCP_OAUTH_CLIENT_SECRET", "GITCODE_MCP_OAUTH_ENCRYPTION_KEY"),
        ("GITCODE_OAUTH_CLIENT_SECRET", "GITCODE_MCP_OAUTH_ENCRYPTION_KEY"),
    ],
)
def test_oauth_app_secret_mcp_secret_and_storage_key_are_independent(oauth_env, target, source):
    oauth_env[target] = oauth_env[source]
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env(oauth_env)
    assert oauth_env[source] not in str(raised.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GITCODE_MCP_OAUTH_CLIENT_SECRET", "short-private-secret"),
        ("GITCODE_OAUTH_CLIENT_SECRET", "private-gitcode-secret\x7f"),
        ("GITCODE_MCP_OAUTH_CLIENT_SECRET", "private-client-secret-value-long-enough\x7f"),
        ("GITCODE_OAUTH_CLIENT_ID", "gitcode-client\x7f"),
    ],
)
def test_secrets_and_client_identifiers_reject_control_characters(oauth_env, name, value):
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env({**oauth_env, name: value})
    assert value not in str(raised.value)


def test_public_host_and_origin_are_added_without_weakening_local_defaults(oauth_env):
    settings = Settings.from_env(
        {**oauth_env, "GITCODE_MCP_PUBLIC_URL": "https://gitcode-mcp.example.com:8443/"}
    )
    assert settings.allowed_hosts == (
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
        "gitcode-mcp.example.com:8443",
    )
    assert settings.allowed_origins == (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
        "https://gitcode-mcp.example.com:8443",
    )


def test_explicit_gateway_hosts_and_origins_are_respected(oauth_env):
    settings = Settings.from_env(
        {
            **oauth_env,
            "GITCODE_MCP_ALLOWED_HOSTS": "gateway.internal:8765",
            "GITCODE_MCP_ALLOWED_ORIGINS": "https://chatgpt.com,https://gitcode-mcp.example.com",
        }
    )
    assert settings.allowed_hosts == ("gateway.internal:8765",)
    assert settings.allowed_origins == ("https://chatgpt.com", "https://gitcode-mcp.example.com")


@pytest.mark.parametrize(
    "value",
    [
        "https://chatgpt.com",
        "https://mcp.example.com:8443",
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://[::1]:*",
        "http://localhost:3000",
    ],
)
def test_explicit_public_and_loopback_origins_are_supported(value):
    assert Settings.from_env({"GITCODE_MCP_ALLOWED_ORIGINS": value}).allowed_origins == (value,)


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://*.example.com",
        "https://example.com:*",
        "https://example.com/path",
        "https://example.com?query=value",
        "https://example.com#fragment",
        "https://user:password@example.com",
        "https://@example.com",
        "https://example.com:invalid",
        "https://example.com:65536",
        "https://example.com:0",
        "https://example.com\x00",
        "https://example.com\x7f",
    ],
)
def test_origin_allowlist_rejects_ambiguous_and_wildcard_public_origins(value):
    with pytest.raises(ConfigurationError):
        Settings.from_env({"GITCODE_MCP_ALLOWED_ORIGINS": value})


def test_existing_bearer_configuration_keeps_its_defaults_and_does_not_enable_oauth():
    settings = Settings.from_env({})
    assert settings.oauth is None
    assert settings.allowed_hosts == ("127.0.0.1:*", "localhost:*", "[::1]:*")
    assert settings.allowed_origins == (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    )
    assert not settings.read_only
    assert settings.token == ""
    configured = Settings.from_env({"GITCODE_TOKEN": "private-existing-pat"})
    assert configured.oauth is None
    assert configured.token == "private-existing-pat"
