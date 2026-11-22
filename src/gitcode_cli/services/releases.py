"""GitCode v5 release metadata. Binary transfers never use the authenticated API client."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from ..client import GitCodeClient
from ..errors import APIError, GCError


def tag_segment(tag: str) -> str:
    if (
        not tag
        or any(part in {"", ".", ".."} for part in tag.split("/"))
        or "\\" in tag
        or any(ord(c) < 32 or ord(c) == 127 for c in tag)
    ):
        raise APIError("Invalid release tag.")
    return quote(tag, safe="")


def release_record(value: Any, tag: str | None = None) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("tag_name"), str) or not value["tag_name"]:
        raise APIError("GitCode did not return a release with a tag.")
    tag_segment(value["tag_name"])
    if tag is not None and value["tag_name"] != tag:
        raise APIError("GitCode returned a different release tag.")
    return value


class ReleaseService:
    def __init__(self, client: GitCodeClient, owner: str, repo: str):
        self.client = client
        self.base = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    def _pages(self, resource: str, key: str, per_page: int, **params: Any) -> Iterator[dict]:
        seen: set[str] = set()
        for page in range(1, 101):
            rows = self.client.get(f"{self.base}/{resource}", params={**params, "page": page, "per_page": per_page})
            if not isinstance(rows, list) or len(rows) > per_page:
                raise APIError("Invalid GitCode collection response.")
            for row in rows:
                identity = row.get(key) if isinstance(row, dict) else None
                if not isinstance(identity, str) or not identity or identity in seen:
                    raise APIError("Missing or repeated identity in GitCode collection.")
                seen.add(identity)
                yield row
            if len(rows) < per_page:
                return
        raise APIError("Pagination limit reached; results are incomplete.")

    def list(self, limit: int, direction: str, exclude_pre: bool) -> list[dict]:
        rows = []
        for row in self._pages("releases", "tag_name", min(limit, 100), direction=direction):
            if exclude_pre:
                if type(row.get("prerelease")) is not bool:
                    raise APIError("Missing prerelease flag; cannot filter releases.")
                if row["prerelease"]:
                    continue
            rows.append(release_record(row))
            if len(rows) == limit:
                break
        return rows

    def require_tag(self, tag: str) -> None:
        tag_segment(tag)
        if not any(row["name"] == tag for row in self._pages("tags", "name", 100)):
            raise APIError("Tag not found; no release was created.")

    def get(self, tag: str | None) -> dict:
        base = self.base + "/releases"
        if tag is None:
            return release_record(self.client.get(base + "/latest", params={"type": "latest"}))
        return release_record(self.client.get(base + "/tags/" + tag_segment(tag)), tag)

    def _confirm_write(self, response: Any, tag: str, payload: dict) -> dict:
        def matches(record: Any) -> bool:
            if (
                not isinstance(record, dict)
                or any(record.get(name) != payload[name] for name in ("name", "body"))
                or record.get("tag_name") != tag
            ):
                return False
            status = payload.get("release_status")
            if status == "latest":
                return record.get("release_status") in ("latest", "lasted") and record.get("prerelease") is False
            if status == "pre":
                return record.get("release_status") == "pre" and record.get("prerelease") is True
            return True

        if matches(response):
            return response
        # Some deployments acknowledge the write without returning the final
        # record. One read can confirm it; never repeat the mutation.
        try:
            observed = self.get(tag)
        except GCError:
            raise APIError("Release write could not be verified; inspect remote state before retrying.") from None
        if not matches(observed):
            raise APIError("Release write did not confirm requested metadata; inspect remote state before retrying.")
        return observed

    def create(self, tag: str, payload: dict) -> dict:
        tag_segment(tag)
        return self._confirm_write(
            self.client.post(self.base + "/releases", json={**payload, "tag_name": tag}), tag, payload
        )

    def edit(self, tag: str, payload: dict) -> dict:
        path = self.base + "/releases/" + tag_segment(tag)
        return self._confirm_write(self.client.patch(path, json=payload), tag, payload)

    def ticket(self, tag: str, name: str) -> dict:
        path = self.base + "/releases/" + tag_segment(tag) + "/upload_url"
        # An error body can contain temporary signatures or callback headers.
        try:
            result = self.client.get(path, params={"file_name": name})
        except APIError as exc:
            raise APIError(f"GitCode refused the upload ticket (HTTP {exc.status_code}).") from None
        if not isinstance(result, dict):
            raise APIError("Invalid upload ticket.")
        return result

    def delete_asset(self, tag: str, asset_id: int) -> None:
        self.client.delete(f"{self.base}/releases/{tag_segment(tag)}/attach_files/{asset_id}")

    def download_metadata(self, tag: str) -> dict:
        # /releases/latest is reserved; never reinterpret the literal tag 'latest'.
        if tag == "latest":
            return self.get(tag)
        try:
            result = self.client.get(self.base + "/releases/" + tag_segment(tag), params={"temp_download_url": "true"})
        except APIError as exc:
            raise APIError(f"GitCode refused release download metadata (HTTP {exc.status_code}).") from None
        return release_record(result, tag)
