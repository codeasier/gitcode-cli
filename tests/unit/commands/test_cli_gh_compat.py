from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "gh-cli-compat"
GH_COMMANDS_PATH = FIXTURES_DIR / "command_baseline.json"
COVERAGE_PATH = FIXTURES_DIR / "coverage.json"

GH_COMMANDS = json.loads(GH_COMMANDS_PATH.read_text(encoding="utf-8"))
COVERAGE = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))

SUPPORTED_TOP_LEVEL_COMMANDS = {"auth", "issue", "pr"}
IGNORED_FLAGS = {"--help"}


def _iter_commands(node: dict) -> list[dict]:
    commands = [node]
    for subcommand in node.get("subcommands", []):
        commands.extend(_iter_commands(subcommand))
    return commands


def _normalize_command_path(path: list[str]) -> str:
    if not path or path[0] != "gh":
        raise AssertionError(f"Unexpected gh command path: {path!r}")
    return " ".join(path[1:])


def _normalize_flag_aliases(flag: dict) -> tuple[str, ...]:
    aliases = tuple(alias for alias in (flag.get("short"), flag.get("long")) if alias and alias not in IGNORED_FLAGS)
    return aliases


def _command_is_selected(command_path: str, selected_groups: dict[str, set[str]]) -> bool:
    parts = command_path.split()
    if len(parts) < 2:
        return False
    group, subcommand = parts[0], parts[1]
    return subcommand in selected_groups.get(group, set())


def _build_excluded_flags() -> dict[str, set[str]]:
    raw_excluded_flags = COVERAGE.get("exclude_flags", {})
    excluded_flags: dict[str, set[str]] = {}
    for group, commands in raw_excluded_flags.items():
        for command_name, entries in commands.items():
            excluded_flags[f"{group} {command_name}"] = {
                entry["name"] if isinstance(entry, dict) else entry for entry in entries
            }
    return excluded_flags


def _build_expected_commands() -> dict[str, dict[str, object]]:
    configured_groups = COVERAGE.get("groups", {})
    selected_groups = {group: set(commands) for group, commands in configured_groups.items()}
    excluded_flags = _build_excluded_flags()

    if not selected_groups:
        raise AssertionError("coverage.json must define a non-empty 'groups' mapping")

    commands: dict[str, dict[str, object]] = {}
    for command in _iter_commands(GH_COMMANDS["root"]):
        path = command.get("path", [])
        if len(path) < 2:
            continue
        normalized = _normalize_command_path(path)
        top_level = path[1]
        if top_level not in SUPPORTED_TOP_LEVEL_COMMANDS:
            continue
        if not _command_is_selected(normalized, selected_groups):
            continue

        flag_alias_groups: list[tuple[str, ...]] = []
        for flag in command.get("flags", []):
            aliases = _normalize_flag_aliases(flag)
            if not aliases:
                continue
            if any(alias in excluded_flags.get(normalized, set()) for alias in aliases):
                continue
            flag_alias_groups.append(aliases)

        commands[normalized] = {
            "group": top_level,
            "subcommand": path[-1],
            "flags": flag_alias_groups,
        }

    expected_command_paths = {
        f"{group} {command_name}" for group, command_names in selected_groups.items() for command_name in command_names
    }
    missing = expected_command_paths.difference(commands)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise AssertionError(f"coverage.json references commands missing from command_baseline.json: {missing_list}")
    return commands


def _group_expected_commands(commands: dict[str, dict[str, object]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for command_path, metadata in commands.items():
        group = metadata["group"]
        if command_path == group:
            continue
        grouped.setdefault(group, []).append(metadata["subcommand"])
    return {group: sorted(set(subcommands)) for group, subcommands in grouped.items()}


def _get_cli_flags(command_path: str) -> set[str]:
    result = CliRunner().invoke(main, command_path.split() + ["--help"])
    flags: set[str] = set()
    for line in result.output.splitlines():
        stripped = line.strip()
        if stripped.startswith("-") or stripped.startswith("--"):
            for part in stripped.split(","):
                token = part.strip().split()[0]
                if token.startswith("-"):
                    flags.add(token)
    if not flags:
        raise AssertionError(
            f"No flags parsed from help output for '{command_path}'. "
            f"Exit code: {result.exit_code}, output: {result.output[:300]!r}"
        )
    return flags


def _assert_subcommands(group: str, expected_subcommands: list[str]) -> None:
    result = CliRunner().invoke(main, [group, "--help"])
    assert result.exit_code == 0, result.output
    for command_name in expected_subcommands:
        assert command_name in result.output


def _assert_command_flags(command_path: str, expected_flags: list[tuple[str, ...]]) -> None:
    flags = _get_cli_flags(command_path)
    for aliases in expected_flags:
        missing = set(aliases).difference(flags)
        assert not missing, f"gh {command_path} flags {sorted(missing)} missing from gc"


EXPECTED_COMMANDS = _build_expected_commands()
EXPECTED_SUBCOMMANDS = _group_expected_commands(EXPECTED_COMMANDS)


class TestCliGhCompatibility:
    @pytest.mark.parametrize(
        ("group", "expected_subcommands"),
        sorted(EXPECTED_SUBCOMMANDS.items()),
    )
    def test_group_subcommands_exist(self, group: str, expected_subcommands: list[str]) -> None:
        _assert_subcommands(group, expected_subcommands)

    @pytest.mark.parametrize(
        ("command_path", "expected_flags"),
        [(command_path, metadata["flags"]) for command_path, metadata in sorted(EXPECTED_COMMANDS.items())],
    )
    def test_command_has_gh_flags(self, command_path: str, expected_flags: list[tuple[str, ...]]) -> None:
        _assert_command_flags(command_path, expected_flags)

    def test_issue_list_rejects_invalid_limit(self) -> None:
        result = CliRunner().invoke(main, ["issue", "list", "-L", "0"])
        assert result.exit_code != 0
        assert "must be greater than 0" in result.output
