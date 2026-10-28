import pytest

from gitcode_mcp.config import ConfigurationError, Settings, repository_name


def test_secrets_are_not_in_repr_and_primary_token_wins():
    settings = Settings.from_env(
        {
            "GITCODE_TOKEN": "primary-secret",
            "GC_TOKEN": "fallback-secret",
            "GITCODE_MCP_HTTP_TOKEN": "http-secret-value-" * 3,
        }
    )
    assert settings.token == "primary-secret"
    assert "secret" not in repr(settings)
    assert Settings.from_env({"GC_TOKEN": "fallback"}).token == "fallback"


def test_policy_configuration():
    settings = Settings.from_env(
        {
            "GITCODE_MCP_READ_ONLY": "true",
            "GITCODE_MCP_ALLOWED_REPOS": "Ascend/msinsight, codeasier/example",
        }
    )
    assert settings.read_only
    assert settings.allowed_repositories == ("Ascend/msinsight", "codeasier/example")
    assert Settings.from_env({}).allowed_repositories == ()
    assert not Settings.from_env({}).read_only


@pytest.mark.parametrize(
    "env",
    [
        {"GITCODE_MCP_READ_ONLY": "maybe"},
        {"GITCODE_TOKEN": "secret\nvalue"},
        {"GITCODE_TOKEN": "secret value"},
        {"GITCODE_MCP_TIMEOUT": "nan"},
        {"GITCODE_MCP_TIMEOUT": "infinity"},
        {"GITCODE_MCP_MAX_RESPONSE_BYTES": "-1"},
        {"GITCODE_MCP_ALLOWED_HOSTS": "*"},
        {"GITCODE_MCP_ALLOWED_HOSTS": "https://example.com"},
        {"GITCODE_MCP_ALLOWED_REPOS": "owner/../repo"},
        {"GITCODE_MCP_HTTP_TOKEN": "short-secret"},
        {"GITCODE_TOKEN": "same-secret-" * 4, "GITCODE_MCP_HTTP_TOKEN": "same-secret-" * 4},
    ],
)
def test_invalid_configuration_does_not_echo_values(env):
    with pytest.raises(ConfigurationError) as error:
        Settings.from_env(env)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "value",
    [
        "https://gitcode.com/owner/repo",
        "../repo",
        "owner/repo.git",
        "owner/../../escape",
        "owner/repo?x=y",
        "-owner/repo",
    ],
)
def test_clone_repository_identifier_is_not_a_url_or_option(value):
    with pytest.raises(ConfigurationError):
        repository_name(value)
