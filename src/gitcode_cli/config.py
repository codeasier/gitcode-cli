from __future__ import annotations

import json
import os
import re
import secrets
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
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
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigError(f"Invalid config file: {CONFIG_PATH}")
        return data
    except (UnicodeError, json.JSONDecodeError) as exc:
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


# Reserved local slot for the original, unverified single-token format.
# It cannot collide with a named GitCode login.
LEGACY = "@legacy"


def valid_login(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", value) is not None
        and value not in {".", ".."}
    )


@dataclass
class Accounts:
    tokens: dict[str, str] = field(repr=False)
    active: str | None

    @classmethod
    def from_config(cls, data: dict) -> Accounts:
        if "accounts" in data or "active_account" in data:
            tokens = data.get("accounts")
            active = data.get("active_account")
            if not isinstance(tokens, dict) or "active_account" not in data or "token" in data:
                raise ConfigError("Invalid account configuration.")
        else:
            tokens = {LEGACY: data["token"]} if "token" in data else {}
            active = LEGACY if tokens else None
        if any(
            not isinstance(token, str)
            or not token.strip()
            or (name != LEGACY and (not valid_login(name) or token in name))
            for name, token in tokens.items()
        ) or (active is not None and (not isinstance(active, str) or active not in tokens)):
            raise ConfigError("Invalid account configuration.")
        return cls(tokens, active)

    def update_config(self, data: dict) -> None:
        for key in ("token", "accounts", "active_account"):
            data.pop(key, None)
        if not self.tokens:
            return
        if self.active == LEGACY and len(self.tokens) == 1:
            data["token"] = self.tokens[LEGACY]
        else:
            # Do not leave a top-level legacy token for older readers to use
            # accidentally when a different account (or none) is selected.
            data.update(accounts=self.tokens, active_account=self.active)

    def require(self, name: str | None) -> str:
        if name is None:
            if self.tokens:
                raise ConfigError("No active saved account. Select one with `gc auth switch --user LOGIN`.")
            raise ConfigError("No token found. Set GC_TOKEN or run `gc auth login`.")
        if name not in self.tokens:
            raise ConfigError("No saved account matches the requested user.")
        return self.tokens[name]


@contextmanager
def edit_accounts() -> Iterator[Accounts]:
    """Serialize read/modify/replace so a concurrent login cannot undo logout."""
    _check_storage_links()
    lock = CONFIG_DIR / ".auth-update.lock"
    try:
        CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise ConfigError("Account configuration is locked; no change was made.") from None
    except OSError:
        raise ConfigError("Unable to securely update account configuration.") from None
    try:
        data = load_config()
        accounts = Accounts.from_config(data)
        yield accounts
        accounts.update_config(data)
        save_config(data)
    finally:
        lock.rmdir()


def get_token(explicit_token: str | None = None) -> str:
    if explicit_token:
        return explicit_token
    for env_name in TOKEN_ENV_VARS:
        value = os.getenv(env_name)
        if value:
            return value
    accounts = Accounts.from_config(load_config())
    return accounts.require(accounts.active)
