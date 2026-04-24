from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import ConfigError

CONFIG_DIR = Path.home() / ".config" / "gc"
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_ENV_VARS = ("GC_TOKEN",)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid config file: {CONFIG_PATH}") from exc


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n")


def get_token(explicit_token: str | None = None) -> str:
    if explicit_token:
        return explicit_token
    for env_name in TOKEN_ENV_VARS:
        value = os.getenv(env_name)
        if value:
            return value
    config = load_config()
    token = config.get("token")
    if token:
        return token
    raise ConfigError("No token found. Set GC_TOKEN or run `gc auth login`.")
