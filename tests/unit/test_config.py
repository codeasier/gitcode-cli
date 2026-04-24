"""Tests for gitcode_cli.config module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gitcode_cli.config import get_token, load_config, save_config
from gitcode_cli.errors import ConfigError


class TestLoadConfig:
    def test_file_does_not_exist(self, tmp_config_dir: Path):
        result = load_config()
        assert result == {}

    def test_valid_json(self, tmp_config_dir: Path):
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps({"token": "file-token"}))
        result = load_config()
        assert result == {"token": "file-token"}

    def test_invalid_json_raises_config_error(self, tmp_config_dir: Path):
        config_path = tmp_config_dir / "config.json"
        config_path.write_text("not valid json")
        with pytest.raises(ConfigError, match="Invalid config file"):
            load_config()


class TestSaveConfig:
    def test_creates_directory_and_writes_file(self, tmp_config_dir: Path):
        save_config({"token": "saved-token"})
        config_path = tmp_config_dir / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data == {"token": "saved-token"}

    def test_overwrites_existing_file(self, tmp_config_dir: Path):
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps({"old": "value"}))
        save_config({"token": "new-token"})
        data = json.loads(config_path.read_text())
        assert data == {"token": "new-token"}


class TestGetToken:
    def test_explicit_token(self):
        assert get_token("explicit") == "explicit"

    def test_from_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GC_TOKEN", "env-token")
        assert get_token() == "env-token"

    def test_from_config_file(self, tmp_config_dir: Path):
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps({"token": "config-token"}))
        assert get_token() == "config-token"

    def test_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GC_TOKEN", "env-token")
        assert get_token("explicit-token") == "explicit-token"

    def test_env_overrides_config(self, tmp_config_dir: Path, monkeypatch: pytest.MonkeyPatch):
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps({"token": "config-token"}))
        monkeypatch.setenv("GC_TOKEN", "env-token")
        assert get_token() == "env-token"

    def test_raises_when_none_available(self, tmp_config_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GC_TOKEN", raising=False)
        config_path = tmp_config_dir / "config.json"
        if config_path.exists():
            config_path.unlink()
        with pytest.raises(ConfigError, match="No token found"):
            get_token()
