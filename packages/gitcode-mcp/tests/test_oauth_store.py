import hashlib
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from gitcode_mcp import oauth_store
from gitcode_mcp.oauth_store import OAuthStore, OAuthStoreError


@pytest.fixture
def key():
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def store(tmp_path, key):
    value = OAuthStore(tmp_path / "oauth.sqlite", key)
    try:
        yield value
    finally:
        value.close()


def future():
    return time.time() + 3600


def count_records(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT COUNT(*) FROM oauth_records").fetchone()[0]


def test_persistence_encrypts_values_and_hashes_keys(tmp_path, key):
    path = tmp_path / "oauth.sqlite"
    lookup = "downstream-token-not-for-disk"
    payload = {"upstream_token": "gitcode-secret-not-for-disk", "subject": "用户 42"}
    store = OAuthStore(path, key)
    with store.transaction() as transaction:
        transaction.put("access", lookup, payload, future())
        assert transaction.get("access", lookup) == payload
        # Exercise the rollback journal while the transaction is still live.
        assert Path(str(path) + "-journal").exists()
        for file in tmp_path.glob("oauth.sqlite*"):
            assert file.stat().st_mode & 0o777 == 0o600
            content = file.read_bytes()
            assert lookup.encode() not in content
            assert payload["upstream_token"].encode() not in content
            assert key.encode() not in content
    store.close()
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT kind, key, value FROM oauth_records").fetchone()
    assert row[:2] == ("access", hashlib.sha256(lookup.encode()).hexdigest())
    assert payload["upstream_token"].encode() not in row[2]
    reopened = OAuthStore(path, key)
    try:
        assert reopened.get("access", lookup) == payload
        assert reopened.get("refresh", lookup) is None
    finally:
        reopened.close()
    assert not Path(str(path) + "-journal").exists()


def test_wrong_key_fails_even_when_no_tokens_exist(tmp_path, key):
    path = tmp_path / "oauth.sqlite"
    OAuthStore(path, key).close()
    wrong = Fernet.generate_key().decode()
    with pytest.raises(OAuthStoreError, match="does not match") as error:
        OAuthStore(path, wrong)
    assert wrong not in str(error.value)
    assert str(path) not in str(error.value)
    reopened = OAuthStore(path, key)
    reopened.put("code", "usable-after-failed-open", {}, future())
    reopened.close()


def test_metadata_corruption_is_not_reset(tmp_path, key):
    path = tmp_path / "oauth.sqlite"
    OAuthStore(path, key).close()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE oauth_metadata SET value = ?", (b"damaged-marker",))
    with pytest.raises(OAuthStoreError, match="metadata is damaged"):
        OAuthStore(path, key)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT value FROM oauth_metadata").fetchone()[0]
            == b"damaged-marker"
        )


def test_ciphertext_corruption_fails_without_consuming_the_record(store):
    store.put("code", "lookup-key", {"token": "upstream-secret"}, future())
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE oauth_records SET value = ?", (b"untrusted-secret-ciphertext",))
    with pytest.raises(OAuthStoreError, match="ciphertext") as error:
        store.pop("code", "lookup-key")
    assert "untrusted-secret" not in str(error.value)
    assert count_records(store.path) == 1


def test_ciphertext_is_bound_to_kind_key_and_expiration(store):
    expiration = future()
    store.put("access", "alice", {"token": "alice-secret"}, expiration)
    store.put("access", "bob", {"token": "bob-secret"}, expiration)
    with sqlite3.connect(store.path) as connection:
        alice = connection.execute(
            "SELECT value FROM oauth_records WHERE key = ?",
            (hashlib.sha256(b"alice").hexdigest(),),
        ).fetchone()[0]
        connection.execute(
            "UPDATE oauth_records SET value = ? WHERE key = ?",
            (alice, hashlib.sha256(b"bob").hexdigest()),
        )
    with pytest.raises(OAuthStoreError, match="belongs to another"):
        store.get("access", "bob")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE oauth_records SET expires = expires + 3600 WHERE key = ?",
            (hashlib.sha256(b"alice").hexdigest(),),
        )
    with pytest.raises(OAuthStoreError, match="belongs to another"):
        store.get("access", "alice")


def test_expired_records_return_none_and_free_capacity(tmp_path, key, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(oauth_store.time, "time", lambda: clock[0])
    store = OAuthStore(tmp_path / "oauth.sqlite", key, max_records=1)
    try:
        store.put("code", "old", {"token": "expired"}, 1001)
        clock[0] = 1001
        assert store.get("code", "old") is None
        assert store.pop("code", "old") is None
        assert count_records(store.path) == 0
        store.put("code", "new", {"token": "live"}, 1002)
        assert store.get("code", "new") == {"token": "live"}
    finally:
        store.close()


def test_expiration_cleanup_is_bounded_per_transaction(tmp_path, key, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(oauth_store.time, "time", lambda: clock[0])
    store = OAuthStore(tmp_path / "oauth.sqlite", key)
    try:
        with store.transaction() as transaction:
            for index in range(250):
                transaction.put("code", str(index), {}, 1001)
        clock[0] = 1002
        assert store.get("code", "missing") is None
        remaining = count_records(store.path)
        assert 0 < remaining < 250
        # Expired lookup is still absent even if that record was outside the cleanup batch.
        assert store.get("code", "249") is None
    finally:
        store.close()


def test_atomic_pop_across_threads_and_connections(tmp_path, key):
    path = tmp_path / "oauth.sqlite"
    first = OAuthStore(path, key)
    second = OAuthStore(path, key)
    try:
        first.put("code", "one-time", {"grant": "one"}, future())
        barrier = threading.Barrier(2)

        def redeem(store):
            barrier.wait(timeout=5)
            return store.pop("code", "one-time")

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(redeem, (first, second)))
        assert results.count({"grant": "one"}) == 1
        assert results.count(None) == 1
    finally:
        first.close()
        second.close()


def test_atomic_refresh_rotation_and_rollback(store):
    store.put("refresh", "old", {"grant": "original"}, future())
    with pytest.raises(RuntimeError, match="cancel exchange"):
        with store.transaction() as transaction:
            assert transaction.pop("refresh", "old") == {"grant": "original"}
            transaction.put("refresh", "new", {"grant": "replacement"}, future())
            raise RuntimeError("cancel exchange")
    assert store.get("refresh", "old") == {"grant": "original"}
    assert store.get("refresh", "new") is None
    with store.transaction() as transaction:
        assert transaction.pop("refresh", "old") == {"grant": "original"}
        transaction.put("refresh", "new", {"grant": "replacement"}, future())
    assert store.get("refresh", "old") is None
    assert store.get("refresh", "new") == {"grant": "replacement"}


def test_quota_never_evicts_live_records_and_allows_updates(tmp_path, key):
    store = OAuthStore(tmp_path / "oauth.sqlite", key, max_records=2)
    try:
        store.put("grant", "one", {"value": 1}, future())
        store.put("grant", "two", {"value": 2}, future())
        with pytest.raises(OAuthStoreError, match="capacity"):
            store.put("grant", "three", {"secret": "not-in-error"}, future())
        store.put("grant", "two", {"value": "updated"}, future())
        assert store.get("grant", "one") == {"value": 1}
        assert store.get("grant", "two") == {"value": "updated"}
        with pytest.raises(OAuthStoreError, match="capacity"):
            with store.transaction() as transaction:
                transaction.delete("grant", "one")
                transaction.put("grant", "three", {}, future())
                transaction.put("grant", "four", {}, future())
        assert store.get("grant", "one") == {"value": 1}
        assert store.get("grant", "three") is None
        store.delete("grant", "one")
        store.put("grant", "three", {}, future())
        assert count_records(store.path) == 2
    finally:
        store.close()


def test_new_paths_are_private_and_existing_parent_permissions_are_unchanged(tmp_path, key):
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o755)
    existing.chmod(0o755)
    path = existing / "private" / "nested" / "oauth.sqlite"
    store = OAuthStore(path, key)
    store.close()
    assert existing.stat().st_mode & 0o777 == 0o755
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.parent.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600


def test_pending_quota_reserves_capacity_for_durable_grants_and_tokens(tmp_path, key):
    store = OAuthStore(tmp_path / "oauth.sqlite", key, max_records=6, max_pending_records=2)
    try:
        store.put("flow", "new-login", {"phase": "authorize"}, future())
        store.put("consent", "other-login", {"phase": "consent"}, future())
        with pytest.raises(OAuthStoreError, match="pending authorization capacity"):
            store.put("state", "overflow", {}, future())
        # Existing pending records can be updated at capacity.
        store.put("flow", "new-login", {"phase": "updated"}, future())
        # Advancing a pending authorization remains an atomic delete/insert.
        with store.transaction() as transaction:
            record = transaction.pop("flow", "new-login")
            transaction.put("state", "upstream-state", record, future())
        assert store.get("flow", "new-login") is None
        assert store.get("state", "upstream-state") == {"phase": "updated"}
        for kind in ("grant", "access", "refresh"):
            store.put(kind, "existing-connection", {"kind": kind}, future())
            assert store.get(kind, "existing-connection") == {"kind": kind}
        with pytest.raises(OAuthStoreError, match="pending authorization capacity"):
            store.put("flow", "still-full", {}, future())
        assert count_records(store.path) == 5
    finally:
        store.close()


def test_expired_pending_records_release_only_the_pending_quota(tmp_path, key, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(oauth_store.time, "time", lambda: clock[0])
    store = OAuthStore(tmp_path / "oauth.sqlite", key, max_records=3, max_pending_records=1)
    try:
        store.put("grant", "existing", {"subject": "alice"}, 2000)
        store.put("flow", "expired-login", {}, 1001)
        clock[0] = 1001
        store.put("flow", "replacement-login", {}, 1002)
        assert store.get("grant", "existing") == {"subject": "alice"}
        assert store.get("flow", "expired-login") is None
        assert store.get("flow", "replacement-login") == {}
    finally:
        store.close()


@pytest.mark.parametrize("broken", [False, True])
def test_database_symlink_is_rejected_without_touching_target(tmp_path, key, broken):
    target = tmp_path / "target"
    if not broken:
        target.write_text("keep this file")
        target.chmod(0o644)
    path = tmp_path / "oauth.sqlite"
    path.symlink_to(target)
    with pytest.raises(OAuthStoreError, match="regular file"):
        OAuthStore(path, key)
    if not broken:
        assert target.read_text() == "keep this file"
        assert target.stat().st_mode & 0o777 == 0o644
    else:
        assert not target.exists()


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_sidecar_symlink_is_rejected_without_touching_target(tmp_path, key, suffix):
    target = tmp_path / "important"
    target.write_text("keep")
    target.chmod(0o644)
    path = tmp_path / "oauth.sqlite"
    Path(str(path) + suffix).symlink_to(target)
    with pytest.raises(OAuthStoreError, match="regular file"):
        OAuthStore(path, key)
    assert target.read_text() == "keep"
    assert target.stat().st_mode & 0o777 == 0o644


def test_parent_symlink_and_nonregular_database_are_rejected(tmp_path, key):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(OAuthStoreError, match="real directories"):
        OAuthStore(linked / "oauth.sqlite", key)
    assert not (real / "oauth.sqlite").exists()
    with pytest.raises(OAuthStoreError, match="regular file"):
        OAuthStore(real, key)


def test_database_hard_link_is_rejected(tmp_path, key):
    original = tmp_path / "original"
    original.write_text("keep")
    linked = tmp_path / "oauth.sqlite"
    os.link(original, linked)
    with pytest.raises(OAuthStoreError, match="hard links"):
        OAuthStore(linked, key)
    assert original.read_text() == "keep"


def test_replaced_database_path_is_rejected(store, tmp_path):
    original = tmp_path / "original.sqlite"
    store.path.rename(original)
    store.path.symlink_to(original)
    with pytest.raises(OAuthStoreError, match="path changed"):
        store.get("code", "missing")


def test_closed_and_escaped_transactions_cannot_be_used(store):
    with store.transaction() as transaction:
        transaction.put("code", "one", {}, future())
    with pytest.raises(OAuthStoreError, match="no longer active"):
        transaction.get("code", "one")
    store.close()
    store.close()
    with pytest.raises(OAuthStoreError, match="closed"):
        store.get("code", "one")


def test_nested_transactions_fail_and_roll_back(store):
    with pytest.raises(OAuthStoreError, match="Nested"):
        with store.transaction() as transaction:
            transaction.put("code", "one", {}, future())
            store.get("code", "one")
    assert store.get("code", "one") is None


def test_bad_configuration_and_payload_errors_do_not_echo_values(tmp_path, key, store):
    with pytest.raises(OAuthStoreError, match="fixed absolute"):
        OAuthStore("relative.sqlite", key)
    with pytest.raises(OAuthStoreError, match="encryption key") as error:
        OAuthStore(tmp_path / "unused.sqlite", "super-private-bad-key")
    assert "super-private" not in str(error.value)
    for maximum in (0, -1, True, 1.5):
        with pytest.raises(OAuthStoreError, match="positive integer"):
            OAuthStore(tmp_path / "unused.sqlite", key, max_records=maximum)
        with pytest.raises(OAuthStoreError, match="positive integer"):
            OAuthStore(tmp_path / "unused.sqlite", key, max_pending_records=maximum)
    for expiration in (float("nan"), float("inf"), "super-private-expiry"):
        with pytest.raises(OAuthStoreError, match="expiration") as error:
            store.put("code", "secret-key", {}, expiration)
        assert "super-private" not in str(error.value)
    with pytest.raises(OAuthStoreError, match="JSON object"):
        store.put("code", "secret-key", {"token": object()}, future())
    assert count_records(store.path) == 0
