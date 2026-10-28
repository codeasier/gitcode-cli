"""Small, encrypted OAuth store for a single-worker HTTP deployment.

Only ciphertext and hashes of caller-supplied keys reach SQLite. Transactions are
synchronous and must not span an ``await``. Keeping the database and its Fernet
key together in a backup is necessary to restore existing authorizations.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_MARKER = b"codeasier-gitcode-mcp.oauth-store.v1"
_CLEANUP_BATCH_SIZE = 100
_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
_PENDING_KINDS = frozenset({"flow", "state", "consent"})


class OAuthStoreError(RuntimeError):
    """Storage failed; messages never include keys, payloads, paths or SQL."""


def _record_key(kind: str, key: str) -> tuple[str, str]:
    if not isinstance(kind, str) or not kind or len(kind) > 128 or "\x00" in kind:
        raise OAuthStoreError("OAuth storage record kind is invalid.")
    if not isinstance(key, str) or not key:
        raise OAuthStoreError("OAuth storage record key is invalid.")
    try:
        kind.encode("utf-8")
        return kind, hashlib.sha256(key.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise OAuthStoreError("OAuth storage record key is invalid.") from None


def _expiry(value: float) -> float:
    if isinstance(value, bool):
        raise OAuthStoreError("OAuth storage expiration is invalid.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise OAuthStoreError("OAuth storage expiration is invalid.") from None
    if not math.isfinite(result):
        raise OAuthStoreError("OAuth storage expiration is invalid.")
    return result


def _prepare_parent(path: Path) -> None:
    """Create only missing directories; never chmod an existing ancestor."""
    for directory in reversed(path.parent.parents):
        _ensure_directory(directory)
    _ensure_directory(path.parent)


def _ensure_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            # A concurrent creator still has to pass the checks below.
            pass
        info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OAuthStoreError("OAuth storage requires real directories, not symlinks.")


def _open_private_file(path: Path, *, create: bool) -> int:
    """Open without following a final symlink, including broken symlinks."""
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if before is not None and (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1):
        raise OAuthStoreError(
            "OAuth storage requires a regular file without symlinks or hard links."
        )
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    if create and before is None:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        after = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or not stat.S_ISREG(after.st_mode)
            or (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino)
            or (before is not None and (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino))
        ):
            raise OAuthStoreError("OAuth storage file changed while opening it.")
        os.fchmod(descriptor, 0o600)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


class OAuthTransaction:
    """Operations valid only inside the transaction which created this object."""

    def __init__(self, store: OAuthStore) -> None:
        self._store = store
        self._thread = threading.get_ident()
        self._active = True

    def _connection(self) -> sqlite3.Connection:
        if not self._active or self._thread != threading.get_ident():
            raise OAuthStoreError("OAuth storage transaction is no longer active in this thread.")
        return self._store._connection()

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        connection = self._connection()
        kind, digest = _record_key(kind, key)
        row = connection.execute(
            "SELECT value, expires FROM oauth_records WHERE kind = ? AND key = ?",
            (kind, digest),
        ).fetchone()
        if row is None:
            return None
        encrypted, expires = row
        expires = _expiry(expires)
        if expires <= time.time():
            connection.execute(
                "DELETE FROM oauth_records WHERE kind = ? AND key = ?", (kind, digest)
            )
            return None
        return self._store._decrypt_record(kind, digest, encrypted, expires)

    def put(self, kind: str, key: str, payload: dict[str, Any], expires_at: float) -> None:
        connection = self._connection()
        kind, digest = _record_key(kind, key)
        expires = _expiry(expires_at)
        encrypted = self._store._encrypt_record(kind, digest, payload, expires)
        exists = connection.execute(
            "SELECT 1 FROM oauth_records WHERE kind = ? AND key = ?", (kind, digest)
        ).fetchone()
        if exists is None:
            count = connection.execute("SELECT COUNT(*) FROM oauth_records").fetchone()[0]
            if count >= self._store.max_records:
                raise OAuthStoreError("OAuth storage capacity has been reached.")
            if kind in _PENDING_KINDS:
                pending = connection.execute(
                    "SELECT COUNT(*) FROM oauth_records WHERE kind IN ('flow', 'state', 'consent')"
                ).fetchone()[0]
                if pending >= self._store.max_pending_records:
                    raise OAuthStoreError("OAuth pending authorization capacity has been reached.")
        connection.execute(
            "INSERT INTO oauth_records(kind, key, value, expires) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(kind, key) DO UPDATE SET value = excluded.value, expires = excluded.expires",
            (kind, digest, encrypted, expires),
        )

    def pop(self, kind: str, key: str) -> dict[str, Any] | None:
        payload = self.get(kind, key)
        if payload is not None:
            self.delete(kind, key)
        return payload

    def delete(self, kind: str, key: str) -> None:
        connection = self._connection()
        kind, digest = _record_key(kind, key)
        connection.execute("DELETE FROM oauth_records WHERE kind = ? AND key = ?", (kind, digest))


class OAuthStore:
    """SQLite + Fernet persistence, with atomic, serialized transactions.

    ``path`` must be absolute. New directories have mode 0700 and the database
    has mode 0600. Existing parent permissions are not changed. SQLite's DELETE
    journal inherits the private database permissions and is removed on commit.
    Existing symlinks or hard links at the database or sidecar paths are refused.
    Pending login records have a separate, smaller quota so unauthenticated
    authorization attempts cannot fill the space reserved for existing grants.
    """

    def __init__(
        self,
        path: str | Path,
        encryption_key: str,
        *,
        max_records: int = 10000,
        max_pending_records: int = 256,
    ) -> None:
        self._lock = threading.RLock()
        self._db: sqlite3.Connection | None = None
        self._in_transaction = False
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise OAuthStoreError("OAuth storage capacity must be a positive integer.")
        if (
            isinstance(max_pending_records, bool)
            or not isinstance(max_pending_records, int)
            or max_pending_records < 1
        ):
            raise OAuthStoreError(
                "OAuth pending authorization capacity must be a positive integer."
            )
        self.max_records = max_records
        self.max_pending_records = min(max_pending_records, max_records)
        try:
            if not isinstance(encryption_key, str):
                raise ValueError
            self._fernet = Fernet(encryption_key.encode("ascii"))
        except (TypeError, ValueError, UnicodeError):
            raise OAuthStoreError("OAuth storage encryption key is invalid.") from None
        try:
            self.path = Path(path)
            if not self.path.is_absolute() or ".." in self.path.parts or "\x00" in str(self.path):
                raise OAuthStoreError("OAuth storage requires a fixed absolute database path.")
            _prepare_parent(self.path)
            descriptor = _open_private_file(self.path, create=True)
            try:
                info = os.fstat(descriptor)
                self._identity = (info.st_dev, info.st_ino)
                was_empty = info.st_size == 0
                self._check_files()
                # mode=rw prevents SQLite from silently creating a replacement path.
                self._db = sqlite3.connect(
                    self.path.as_uri() + "?mode=rw",
                    uri=True,
                    isolation_level=None,
                    check_same_thread=False,
                    timeout=5,
                )
                self._check_files()
            finally:
                os.close(descriptor)
            connection = self._connection()
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA synchronous = FULL")
            mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if mode.lower() != "delete":
                raise OAuthStoreError("OAuth storage could not enable private rollback journaling.")
            self._initialize(was_empty)
        except OAuthStoreError:
            self.close()
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError):
            self.close()
            raise OAuthStoreError("OAuth storage could not be opened securely.") from None

    def _connection(self) -> sqlite3.Connection:
        if self._db is None:
            raise OAuthStoreError("OAuth storage is closed.")
        return self._db

    def _check_files(self) -> None:
        info = self.path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != self._identity
        ):
            raise OAuthStoreError("OAuth storage database path changed.")
        for suffix in _SIDECAR_SUFFIXES:
            sidecar = Path(str(self.path) + suffix)
            try:
                sidecar.lstat()
            except FileNotFoundError:
                continue
            descriptor = _open_private_file(sidecar, create=False)
            os.close(descriptor)

    def _initialize(self, was_empty: bool) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables and was_empty:
                connection.execute(
                    "CREATE TABLE oauth_metadata(id INTEGER PRIMARY KEY CHECK(id = 1), value BLOB NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE oauth_records("
                    "kind TEXT NOT NULL, key TEXT NOT NULL, value BLOB NOT NULL, expires REAL NOT NULL, "
                    "PRIMARY KEY(kind, key))"
                )
                connection.execute(
                    "CREATE INDEX oauth_records_expiration ON oauth_records(expires)"
                )
                connection.execute(
                    "INSERT INTO oauth_metadata(id, value) VALUES (1, ?)",
                    (self._fernet.encrypt(_MARKER),),
                )
            elif tables != {"oauth_metadata", "oauth_records"}:
                raise OAuthStoreError("OAuth storage format is not recognized.")
            marker = connection.execute("SELECT value FROM oauth_metadata WHERE id = 1").fetchone()
            try:
                if marker is None or self._fernet.decrypt(marker[0]) != _MARKER:
                    raise InvalidToken
            except (InvalidToken, TypeError, ValueError):
                raise OAuthStoreError(
                    "OAuth storage encryption key does not match or metadata is damaged."
                ) from None
            self._cleanup_expired(connection)
            connection.commit()
        except BaseException:
            self._rollback()
            raise

    def _cleanup_expired(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM oauth_records WHERE rowid IN ("
            "SELECT rowid FROM oauth_records WHERE expires <= ? ORDER BY expires LIMIT ?)",
            (time.time(), _CLEANUP_BATCH_SIZE),
        )

    def _encrypt_record(
        self, kind: str, digest: str, payload: dict[str, Any], expires: float
    ) -> bytes:
        if not isinstance(payload, dict):
            raise OAuthStoreError("OAuth storage payload must be a JSON object.")
        try:
            encoded = json.dumps(
                {"kind": kind, "key": digest, "expires": expires, "payload": payload},
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise OAuthStoreError("OAuth storage payload must be a JSON object.") from None
        return self._fernet.encrypt(encoded)

    def _decrypt_record(
        self, kind: str, digest: str, encrypted: bytes, expires: float
    ) -> dict[str, Any]:
        try:
            envelope = json.loads(self._fernet.decrypt(encrypted))
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"kind", "key", "expires", "payload"}
                or envelope["kind"] != kind
                or envelope["key"] != digest
                or envelope["expires"] != expires
                or not isinstance(envelope["payload"], dict)
            ):
                raise ValueError
            return envelope["payload"]
        except (InvalidToken, TypeError, ValueError, UnicodeError, RecursionError):
            raise OAuthStoreError(
                "OAuth storage ciphertext is damaged or belongs to another record."
            ) from None

    def _rollback(self) -> None:
        connection = self._connection()
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error:
            try:
                connection.close()
            finally:
                self._db = None
            raise OAuthStoreError(
                "OAuth storage rollback failed; reopen the store before use."
            ) from None

    @contextmanager
    def transaction(self) -> Iterator[OAuthTransaction]:
        """Hold the lock and a write transaction; never await within this block."""
        with self._lock:
            connection = self._connection()
            if self._in_transaction:
                raise OAuthStoreError("Nested OAuth storage transactions are not supported.")
            transaction: OAuthTransaction | None = None
            try:
                self._check_files()
                connection.execute("BEGIN IMMEDIATE")
                self._in_transaction = True
                transaction = OAuthTransaction(self)
                self._cleanup_expired(connection)
                yield transaction
                connection.commit()
            except (OSError, sqlite3.Error):
                self._rollback()
                raise OAuthStoreError("OAuth storage transaction failed.") from None
            except BaseException:
                self._rollback()
                raise
            finally:
                if transaction is not None:
                    transaction._active = False
                self._in_transaction = False

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        with self.transaction() as transaction:
            return transaction.get(kind, key)

    def put(self, kind: str, key: str, payload: dict[str, Any], expires_at: float) -> None:
        with self.transaction() as transaction:
            transaction.put(kind, key, payload, expires_at)

    def pop(self, kind: str, key: str) -> dict[str, Any] | None:
        with self.transaction() as transaction:
            return transaction.pop(kind, key)

    def delete(self, kind: str, key: str) -> None:
        with self.transaction() as transaction:
            transaction.delete(kind, key)

    def close(self) -> None:
        with self._lock:
            if self._in_transaction:
                raise OAuthStoreError("Cannot close OAuth storage during a transaction.")
            if self._db is not None:
                try:
                    self._db.close()
                except sqlite3.Error:
                    raise OAuthStoreError("OAuth storage could not close cleanly.") from None
                finally:
                    self._db = None
