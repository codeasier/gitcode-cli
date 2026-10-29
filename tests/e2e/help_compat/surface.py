"""Parse displayed help and compare only fields present in the pinned gh fixture."""

from __future__ import annotations

import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
FLAG_ROW = re.compile(r"(?P<aliases>--?[\w-]+(?:,\s*--?[\w-]+)*)(?:\s+(?P<value>.+))?$")
CATEGORIES = {"deferred", "platform", "semantics", "wording", "extension"}
SECTIONS = {"USAGE", "ALIASES", "FLAGS", "INHERITED FLAGS", "ARGUMENTS", "JSON FIELDS", "EXAMPLES", "LEARN MORE"}


def normalize(text: str) -> str:
    text = ANSI.sub("", text)
    text = re.sub(r"\b(?:GitCode|GitHub)\b", "platform", text)
    text = re.sub(r"\b(?:gc|gh|gitcode)\b", "cli", text)
    return " ".join(text.split()).rstrip(".")


def _rows(lines: list[str], *, flags: bool) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_row = stripped.startswith("-") if flags else bool(re.match(r"[\w-]+:", stripped))
        if is_row:
            cells = re.split(r"\s{2,}", stripped, maxsplit=1)
            rows.append((cells[0], cells[1] if len(cells) > 1 else ""))
        else:
            assert rows, f"Orphan help continuation: {line!r}"
            name, description = rows[-1]
            rows[-1] = (name, f"{description} {stripped}")
    return rows


def parse_help(text: str) -> dict:
    sections: dict[str, list[str]] = {"INTRO": []}
    section = "INTRO"
    for line in ANSI.sub("", text).splitlines():
        if re.fullmatch(r"[A-Z][A-Z ]+", line):
            assert line in SECTIONS or line.endswith("COMMANDS"), f"Unknown help section: {line}"
            assert line not in sections, f"Duplicate help section: {line}"
            section = line
            sections[section] = []
        else:
            assert section == "INTRO" or not line or line.startswith(" "), f"Unrecognized help structure: {line}"
            sections[section].append(line)
    assert sections.get("USAGE"), "Help must contain a USAGE section"
    result = {
        "summary": normalize(" ".join(sections["INTRO"])),
        "usage": normalize(" ".join(sections["USAGE"])),
        "aliases": sorted(normalize(line) for line in sections.get("ALIASES", []) if line.strip()),
        "commands": {},
        "flags": {},
    }
    for title, lines in sections.items():
        if title.endswith("COMMANDS"):
            for label, description in _rows(lines, flags=False):
                assert label.endswith(":"), f"Malformed command row: {label}"
                name = label[:-1]
                assert name not in result["commands"], f"Duplicate command: {name}"
                result["commands"][name] = normalize(description)
        elif title in {"FLAGS", "INHERITED FLAGS"}:
            for label, _description in _rows(lines, flags=True):
                match = FLAG_ROW.fullmatch(label)
                assert match, f"Malformed flag row: {label}"
                aliases = [part.strip() for part in match["aliases"].split(",")]
                target = next((alias for alias in aliases if alias.startswith("--")), aliases[0])
                for alias in aliases:
                    assert alias not in result["flags"], f"Duplicate flag: {alias}"
                    result["flags"][alias] = {"target": target, "takes_value": match["value"] is not None}
    return result


def baseline_surface(node: dict) -> dict:
    flags = {}
    for flag in node["flags"]:
        target = flag["long"] or flag["short"]
        for alias in (flag["short"], flag["long"]):
            if alias:
                assert alias not in flags, f"Duplicate baseline flag: {alias}"
                flags[alias] = {"target": target, "takes_value": flag["value"] is not None}
    return {
        "flags": flags,
        "commands": {child["path"][-1]: normalize(child["summary"]) for child in node["subcommands"]},
    }


def _reason(entry: dict) -> None:
    assert entry["category"] in CATEGORIES, f"Unrecognized difference category: {entry}"
    assert isinstance(entry["reason"], str) and entry["reason"].strip(), f"Missing difference reason: {entry}"


def expected_surface(node: dict, policy: dict) -> dict:
    """Apply explicit, non-stale differences to the independent gh fixture."""
    expected = baseline_surface(node)
    for field in ("flags", "commands"):
        for key, difference in policy.get(f"missing_{field}", {}).items():
            _reason(difference)
            assert key in expected[field], f"Stale missing {field} exception: {key}"
            del expected[field][key]
        for key, difference in policy.get(f"additional_{field}", {}).items():
            _reason(difference)
            assert key not in expected[field], f"Stale additional {field} exception: {key}"
            expected[field][key] = difference["value"]
        for key, difference in policy.get(f"changed_{field}", {}).items():
            _reason(difference)
            assert key in expected[field], f"Unknown changed {field} exception: {key}"
            assert expected[field][key] != difference["value"], f"Stale changed {field} exception: {key}"
            expected[field][key] = difference["value"]
    return expected


def assert_surface(actual: dict, node: dict, policy: dict) -> None:
    expected = expected_surface(node, policy)
    for field in ("flags", "commands"):
        assert actual[field] == expected[field], f"Unregistered {field} drift: {actual[field]} != {expected[field]}"
    # Baseline summaries are parent-menu labels, already compared in commands.
    # They are not the full introductory prose of this command's own help.
    # These two fields are deliberately gc invariants: the gh snapshot lacks them.
    assert actual["usage"] == policy["gc_invariants"]["usage"], "gc usage changed"
    assert actual["aliases"] == policy["gc_invariants"]["aliases"], "gc aliases changed"
