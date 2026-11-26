"""Direct gc changed-file filtering; no diff parsing or filesystem access."""

from __future__ import annotations

import re

import click

_MAX_PATTERNS = 32
_MAX_PATTERN_BYTES = 512
_ComponentPattern = tuple[tuple[int, re.Pattern[str]], ...]
_PathPattern = tuple[_ComponentPattern, ...]


_PATTERN_USAGE = (
    "--exclude accepts nonempty printable paths, '*' or '?' per component, and a backslash "
    "before '*', '?', '[' or ']' to match that character literally. "
    "No character classes, other escapes, commas or double quotes. Repeat the flag for multiple patterns."
)


def _compile_component(part: str) -> _ComponentPattern:
    # Only fixed-width chunks become regexes; handle '*' separately. Count
    # filename code points, not pattern characters (an escape consumes two).
    chunks: list[tuple[int, re.Pattern[str]]] = []
    tokens: list[str] = []
    chars = iter(part)
    for ch in chars:
        if ch == "*":
            chunks.append((len(tokens), re.compile("".join(tokens))))
            tokens.clear()
        elif ch == "?":
            tokens.append("[^/]")
        elif ch == "\\":
            literal = next(chars, None)
            if literal not in ("*", "?", "[", "]"):
                raise click.UsageError(_PATTERN_USAGE)
            tokens.append(re.escape(literal))
        elif ch == "[":
            raise click.UsageError(_PATTERN_USAGE)
        else:
            tokens.append(re.escape(ch))
    chunks.append((len(tokens), re.compile("".join(tokens))))
    return tuple(chunks)


def _parse_pattern(value: str) -> _PathPattern:
    try:
        too_long = len(value) > _MAX_PATTERN_BYTES or len(value.encode("utf-8")) > _MAX_PATTERN_BYTES
    except UnicodeEncodeError:
        raise click.UsageError("--exclude patterns must be valid UTF-8.") from None
    if too_long:
        raise click.UsageError(f"Each --exclude pattern must be at most {_MAX_PATTERN_BYTES} UTF-8 bytes.")
    if not value or not value.isprintable() or "," in value or '"' in value:
        raise click.UsageError(_PATTERN_USAGE)
    return tuple(_compile_component(part) for part in value.split("/"))


def exclude_patterns(values: tuple[str, ...]) -> tuple[_PathPattern, ...]:
    if len(values) > _MAX_PATTERNS:
        raise click.UsageError(f"Use at most {_MAX_PATTERNS} --exclude patterns.")
    return tuple(_parse_pattern(value) for value in values)


def _matches_component(name: str, pattern: _ComponentPattern) -> bool:
    if len(pattern) == 1:
        return pattern[0][1].fullmatch(name) is not None
    (start, prefix), *middle, (suffix_width, suffix) = pattern
    end = len(name) - suffix_width
    if start > end or not prefix.match(name) or not suffix.fullmatch(name, end):
        return False
    # Fixed-width chunks: taking each earliest match leaves the most room
    # for all later chunks. No recursive/backtracking expansion of '*'.
    for _, chunk in middle:
        match = chunk.search(name, start, end)
        if match is None:
            return False
        start = match.end()
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
