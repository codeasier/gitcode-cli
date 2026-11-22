"""Repository task labels, not issue/PR assignments or project discovery tags."""

from __future__ import annotations

from urllib.parse import quote

from ..client import GitCodeClient
from ..errors import APIError, GCError
from ..repo import validate_gitcode_repo


def validate_name(name: str) -> str:
    if (
        not name
        or name != name.strip()
        or name in {".", ".."}
        or any(c in "/\\%," or not c.isprintable() for c in name)
    ):
        raise APIError("Expected one unambiguous label name (no path separators, commas, escapes or controls).")
    return name


class LabelService:
    def __init__(self, client: GitCodeClient, owner: str, repo: str):
        self.client = client
        owner, repo = validate_gitcode_repo(None, owner, repo)
        self.path = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/labels"

    def list(self, limit: int | None = 30, search: str = "") -> list[dict]:
        if limit is not None and not 1 <= limit <= 10000:
            raise ValueError("Label result limit must be between 1 and 10000.")
        per_page = min(100, limit) if not search and limit is not None else 100
        seen: set[str] = set()
        matches: list[dict] = []
        for page in range(1, 101):
            result = self.client.get(self.path, params={"page": page, "per_page": per_page})
            if not isinstance(result, list) or len(result) > per_page:
                raise APIError("Unexpected repository label page.")
            for row in result:
                if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
                    raise APIError("Missing repository label name.")
                if row["name"] in seen:
                    raise APIError("GitCode returned overlapping label pages.")
                seen.add(row["name"])
                if search.casefold() in row["name"].casefold():
                    matches.append(row)
            if len(result) < per_page or (limit is not None and len(matches) >= limit):
                return matches[:limit]
        raise APIError("Label pagination exceeded its safety bound; collection is incomplete.")

    def create(self, name: str, color: str) -> None:
        result = self.client.post(self.path, json={"name": validate_name(name), "color": color})
        self._confirm(result, name, color)

    def edit(self, original: str, name: str | None, color: str | None) -> None:
        params = {}
        if name is not None:
            params["name"] = validate_name(name)
        if color is not None:
            params["color"] = color
        result = self.client.patch(f"{self.path}/{quote(validate_name(original), safe='')}", params=params)
        self._confirm(result, name or original, color)

    def delete(self, name: str) -> None:
        result = self.client.delete(f"{self.path}/{quote(validate_name(name), safe='')}")
        if result not in (None, {}):
            raise APIError("Label deletion response was not recognized. Verify remote state before retrying.")
        try:
            remaining = self.list(limit=None)
        except GCError:
            raise APIError("Could not verify label deletion. Verify remote state before retrying.") from None
        if any(row["name"].casefold() == name.casefold() for row in remaining):
            raise APIError("The label remains after deletion. Verify remote state before retrying.")

    @staticmethod
    def _confirm(result, expected_name, color):
        if (
            not isinstance(result, dict)
            or type(result.get("id")) is not int
            or result["id"] < 1
            or result.get("name") != expected_name
            or (color and str(result.get("color")).lower() != color.lower())
        ):
            raise APIError("Label mutation was not confirmed. Verify remote state before retrying.")
