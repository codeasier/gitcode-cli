from __future__ import annotations

import re

import pytest

from gitcode_cli.adapters.capabilities import CAPABILITY_MESSAGES
from gitcode_cli.compat import CompatStatus, iter_entries
from gitcode_cli.compat.registry import _ENTRIES


def _commands_source() -> dict[str, str]:
    """Return ``{short_flag: source_text}`` for each commands module."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "src" / "gitcode_cli" / "commands"
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py"))}


def _pending_calls(source: str) -> set[str]:
    """Return every literal string passed to ``_pending_gh_compat(...)``."""
    pattern = re.compile(r'_pending_gh_compat\(\s*["\']([^"\']+)["\']\s*\)')
    return {match.group(1) for match in pattern.finditer(source)}


def _unsupported_calls(source: str) -> set[str]:
    """Return every literal string passed to ``unsupported(...)``."""
    pattern = re.compile(r'\bunsupported\(\s*["\']([^"\']+)["\']\s*\)')
    return {match.group(1) for match in pattern.finditer(source)}


class TestRegistryBasics:
    def test_entries_present(self) -> None:
        # Sanity: a non-trivial registry. 100 entries ensures no accidental wipe.
        assert len(_ENTRIES) >= 100

    def test_no_duplicate_command_flag_pairs(self) -> None:
        seen: set[tuple[str, str | None]] = set()
        for entry in _ENTRIES:
            key = (entry.command, entry.flag)
            assert key not in seen, f"duplicate entry: {key}"
            seen.add(key)

    def test_status_keys_only(self) -> None:
        for entry in _ENTRIES:
            assert isinstance(entry.status, CompatStatus)

    def test_pending_entries_have_pending_key(self) -> None:
        for entry in _ENTRIES:
            if entry.status is CompatStatus.PENDING:
                assert entry.pending_key, f"{entry.label()}: PENDING entries must set pending_key"

    def test_unsupported_entries_have_capability_key(self) -> None:
        for entry in _ENTRIES:
            if entry.status is CompatStatus.UNSUPPORTED:
                assert entry.unsupported_key, f"{entry.label()}: UNSUPPORTED entries must set unsupported_key"
                assert entry.unsupported_key in CAPABILITY_MESSAGES, (
                    f"{entry.label()}: capability key {entry.unsupported_key!r} missing from CAPABILITY_MESSAGES"
                )

    def test_other_statuses_have_no_guard_keys(self) -> None:
        for entry in _ENTRIES:
            if entry.status is CompatStatus.PENDING:
                continue
            assert entry.pending_key is None, f"{entry.label()}: pending_key only valid for PENDING entries"
            if entry.status is CompatStatus.UNSUPPORTED:
                continue
            assert entry.unsupported_key is None, f"{entry.label()}: unsupported_key only valid for UNSUPPORTED entries"


class TestRegistryMatchesRuntime:
    """Cross-check the registry against the command layer."""

    @pytest.fixture(scope="class")
    def sources(self) -> dict[str, str]:
        return _commands_source()

    def test_every_pending_entry_has_runtime_guard(self, sources: dict[str, str]) -> None:
        pending_keys = {entry.pending_key for entry in _ENTRIES if entry.pending_key}
        actual_pending: set[str] = set()
        for text in sources.values():
            actual_pending.update(_pending_calls(text))
        missing = pending_keys - actual_pending
        assert not missing, "pending entries without a matching `_pending_gh_compat()` call: " + ", ".join(
            sorted(missing)
        )

    def test_every_runtime_pending_has_registry_entry(self, sources: dict[str, str]) -> None:
        actual_pending: set[str] = set()
        for text in sources.values():
            actual_pending.update(_pending_calls(text))
        pending_keys = {entry.pending_key for entry in _ENTRIES if entry.pending_key}
        orphan = actual_pending - pending_keys
        assert not orphan, "`_pending_gh_compat()` calls without a registry entry: " + ", ".join(sorted(orphan))

    def test_every_unsupported_entry_raises_with_capability_key(self, sources: dict[str, str]) -> None:
        unsupported_keys = {entry.unsupported_key for entry in _ENTRIES if entry.unsupported_key}
        actual_unsupported: set[str] = set()
        for text in sources.values():
            actual_unsupported.update(_unsupported_calls(text))
        missing = unsupported_keys - actual_unsupported
        assert not missing, "unsupported entries without a matching `unsupported()` call: " + ", ".join(sorted(missing))

    def test_capability_message_exists_for_each_unsupported_entry(self) -> None:
        for entry in _ENTRIES:
            if entry.unsupported_key is None:
                continue
            assert entry.unsupported_key in CAPABILITY_MESSAGES, (
                f"{entry.label()}: {entry.unsupported_key!r} not in CAPABILITY_MESSAGES"
            )


class TestPendingFlagsBehaveAsPending:
    """End-to-end: invoking a PENDING flag raises the documented message."""

    @pytest.mark.parametrize(
        ("args", "flag_name"),
        [
            (["pr", "comment", "1", "--create-if-none"], "pr comment --create-if-none"),
            (["pr", "comment", "1", "--delete-last"], "pr comment --delete-last"),
            (["pr", "comment", "1", "--edit-last"], "pr comment --edit-last"),
            (["pr", "comment", "1", "--yes"], "pr comment --yes"),
            (["pr", "reopen", "1", "--comment", "reopening"], "pr reopen --comment"),
            (["pr", "diff", "1", "--name-only"], "pr diff --name-only"),
            (["pr", "diff", "1", "--patch"], "pr diff --patch"),
            (["pr", "checkout", "1", "--detach"], "pr checkout --detach"),
            (["pr", "checkout", "1", "--force"], "pr checkout --force"),
            (["auth", "status", "--json", "token"], "auth status --json"),
            (["auth", "status", "--jq", ".token"], "auth status --jq"),
            (["auth", "status", "--template", "{{.token}}"], "auth status --template"),
        ],
    )
    def test_pending_flag_invocation_fails(self, args: list[str], flag_name: str) -> None:
        # Paranoia: this list must mirror every PENDING entry whose guard we want to
        # verify at runtime. The full registry→guard consistency is enforced
        # separately in TestRegistryMatchesRuntime; this list catches the case
        # where a guard message drifted.
        from click.testing import CliRunner

        from gitcode_cli.cli import main

        result = CliRunner().invoke(main, args)
        assert result.exit_code != 0, result.output
        assert f"gh-compatible command/flag '{flag_name}' is recognized but not implemented yet." in result.output


@pytest.mark.parametrize(
    "entry",
    [e for e in iter_entries() if e.status is CompatStatus.PENDING],
)
def test_every_pending_entry_has_runtime_match(entry) -> None:
    """Each PENDING entry's pending_key must show up in some command module."""
    sources = _commands_source()
    for text in sources.values():
        if entry.pending_key and entry.pending_key in _pending_calls(text):
            return
    pytest.fail(f"{entry.label()}: pending_key {entry.pending_key!r} has no matching `_pending_gh_compat()` call")


@pytest.mark.parametrize(
    "entry",
    [e for e in iter_entries() if e.status is CompatStatus.UNSUPPORTED],
)
def test_every_unsupported_entry_has_runtime_match(entry) -> None:
    sources = _commands_source()
    for text in sources.values():
        if entry.unsupported_key and entry.unsupported_key in _unsupported_calls(text):
            return
    pytest.fail(f"{entry.label()}: unsupported_key {entry.unsupported_key!r} has no matching `unsupported()` call")
