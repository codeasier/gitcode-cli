"""Tests for gitcode_cli.errors module."""

from __future__ import annotations

import pytest

from gitcode_cli.errors import APIError, AuthError, ConfigError, GCError, RepoResolutionError


class TestExceptions:
    def test_gc_error_can_be_raised_and_caught(self):
        with pytest.raises(GCError, match="base error"):
            raise GCError("base error")

    def test_config_error_is_gc_error(self):
        with pytest.raises(GCError):
            raise ConfigError("config error")
        with pytest.raises(ConfigError, match="config error"):
            raise ConfigError("config error")

    def test_auth_error_is_gc_error(self):
        with pytest.raises(GCError):
            raise AuthError("auth error")
        with pytest.raises(AuthError, match="auth error"):
            raise AuthError("auth error")

    def test_repo_resolution_error_is_gc_error(self):
        with pytest.raises(GCError):
            raise RepoResolutionError("repo error")
        with pytest.raises(RepoResolutionError, match="repo error"):
            raise RepoResolutionError("repo error")

    def test_api_error_is_gc_error(self):
        with pytest.raises(GCError):
            raise APIError("api error")
        with pytest.raises(APIError, match="api error"):
            raise APIError("api error")

    def test_api_error_status_code(self):
        err = APIError("not found", status_code=404)
        assert err.status_code == 404

    def test_api_error_status_code_none(self):
        err = APIError("unknown")
        assert err.status_code is None

    def test_api_error_message(self):
        err = APIError("something failed", status_code=500)
        assert str(err) == "something failed"
