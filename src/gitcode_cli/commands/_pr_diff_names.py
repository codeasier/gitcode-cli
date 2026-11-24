"""Direct gc changed-file filtering; no diff parsing or filesystem access."""

from __future__ import annotations

import click

_MAX_PATTERNS = 32
_MAX_PATTERN_BYTES = 512
_ComponentPattern = tuple[str, ...]
_PathPattern = tuple[_ComponentPattern, ...]


def _parse_pattern(value: str) -> _PathPattern:
    try:
        too_long = len(value) > _MAX_PATTERN_BYTES or len(value.encode("utf-8")) > _MAX_PATTERN_BYTES
    except UnicodeEncodeError:
        raise click.UsageError("--exclude patterns must be valid UTF-8.") from None
    if too_long:
        raise click.UsageError(f"Each --exclude pattern must be at most {_MAX_PATTERN_BYTES} UTF-8 bytes.")
    # Don't guess at Go path.Match's classes/escapes or pflag's CSV grammar.
    if not value or not value.isprintable() or any(ch in '?[\\,"' for ch in value):
        raise click.UsageError(
            "--exclude accepts nonempty printable text and '*' within path components. "
            "No ?, classes, escapes, commas or double quotes. "
            "Repeat the flag for multiple patterns."
        )
    return tuple(tuple(part.split("*")) for part in value.split("/"))


def exclude_patterns(values: tuple[str, ...]) -> tuple[_PathPattern, ...]:
    if len(values) > _MAX_PATTERNS:
        raise click.UsageError(f"Use at most {_MAX_PATTERNS} --exclude patterns.")
    return tuple(_parse_pattern(value) for value in values)


def _matches_component(name: str, pattern: _ComponentPattern) -> bool:
    if len(pattern) == 1:
        return name == pattern[0]
    prefix, *middle, suffix = pattern
    start, end = len(prefix), len(name) - len(suffix)
    if start > end or not name.startswith(prefix) or not name.endswith(suffix):
        return False
    # Anchor the outer literals, then take the earliest occurrence of each
    # interior literal. That leaves the most space for the rest: no regex or
    # backtracking, even for many stars followed by a nonmatching literal.
    for literal in middle:
        start = name.find(literal, start, end)
        if start == -1:
            return False
        start += len(literal)
    return True


def _matches_path(parts: list[str], pattern: _PathPattern) -> bool:
    # Match slash-delimited components independently: even '**' cannot
    # cross a separator.
    return len(parts) == len(pattern) and all(_matches_component(s, p) for s, p in zip(parts, pattern))


def excluded(path: str, patterns: tuple[_PathPattern, ...]) -> bool:
    parts = path.split("/")
    # Like Go path.Base, ignore trailing slashes for the basename only.
    # A nonempty path made entirely of slashes has basename "/".
    base = parts[-1] or path.rstrip("/").rsplit("/", 1)[-1]
    basename = [base] if base else ["", ""]
    return any(_matches_path(parts, p) or (len(parts) > 1 and _matches_path(basename, p)) for p in patterns)
