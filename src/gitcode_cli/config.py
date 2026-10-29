from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from .errors import ConfigError

CONFIG_DIR = Path.home() / ".config" / "gc"
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_ENV_VARS = ("GC_TOKEN",)


def load_config() -> dict:
    _check_storage_links()
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid config file: {CONFIG_PATH}") from exc


def save_config(data: dict) -> None:
    content = json.dumps(data, indent=2) + "\n"
    try:
        _check_storage_links()
        CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            _save_private_posix(content)
        else:
            _save_atomic(content)
    except OSError:
        raise ConfigError("Unable to securely save token configuration.") from None


def _check_storage_links() -> None:
    # Do not traverse a user-configured directory link or replace a linked token
    # file. Atomic replacement also avoids modifying another hardlink's inode.
    for path in (CONFIG_DIR.parent, CONFIG_DIR, CONFIG_PATH):
        if path.is_symlink():
            raise ConfigError("Refusing linked token configuration storage.")
    if CONFIG_PATH.exists():
        info = CONFIG_PATH.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ConfigError("Token configuration must be a regular, unlinked file.")


def _save_private_posix(content: str) -> None:
    directory = os.open(CONFIG_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = ".config-" + secrets.token_hex(16)
    try:
        if os.fstat(directory).st_uid != os.getuid():
            raise ConfigError("Token configuration directory is not owned by this user.")
        os.fchmod(directory, 0o700)
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, CONFIG_PATH.name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(name, dir_fd=directory)
    finally:
        os.close(directory)


def _save_atomic(content: str) -> None:
    # Windows uses the user's profile ACL; POSIX modes are enforced above.
    descriptor, name = tempfile.mkstemp(prefix=".config-", dir=CONFIG_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, CONFIG_PATH)
    finally:
        Path(name).unlink(missing_ok=True)


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
