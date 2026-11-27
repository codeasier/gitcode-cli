"""Release asset selection, credential-isolated streaming and integrity checks."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from fnmatch import fnmatchcase
from http.client import HTTPException
from pathlib import PureWindowsPath
from typing import Any, BinaryIO, Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, unquote, unquote_plus, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .errors import GCError

# Signed storage and binary traffic use a separate opener, not the API client's
# query authentication, cookies, logging or any automatically forwarded headers.
_OBS_HOST = re.compile(r"(?:[a-z0-9-]+\.)?obs\.[a-z0-9-]+\.myhuaweicloud\.com")
_WEB_HOSTS = {"gitcode.com", "raw.gitcode.com", "api.gitcode.com", "atomgit.com", "raw.atomgit.com", "api.atomgit.com"}
_UPLOAD_HEADERS = {"content-type", "x-obs-meta-project-id", "x-obs-acl", "x-obs-callback"}
_REDIRECTS = {301, 302, 303, 307, 308}


def safe_name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(".")
        or value.endswith((".", " "))
        or PureWindowsPath(value).is_reserved()
        or any(c in '<>:"/\\|?*' or unicodedata.category(c).startswith("C") for c in value)
    ):
        raise GCError("Unsafe release asset filename.")
    return value


def reject_reflected_credential(value: Any, secret: str) -> None:
    if isinstance(value, str) and secret and (secret in value or secret in unquote_plus(value)):
        raise GCError("Refused reflected API credentials in release transfer metadata.")


def asset_url(value: Any, *, upload: bool = False) -> str:
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 or c == "\\" for c in value):
        raise GCError("Invalid release transfer URL.")
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        allowed = bool(_OBS_HOST.fullmatch(host)) or host in _WEB_HOSTS
        if (
            not allowed
            or parts.scheme != "https"
            or parts.port not in (None, 443)
            or parts.username is not None
            or parts.fragment
            or (
                upload
                and not (
                    _OBS_HOST.fullmatch(host)
                    or (host in {"api.gitcode.com", "api.atomgit.com"} and parts.path.startswith("/upload/"))
                )
            )
            or any(
                k.lower() in {"access_token", "private-token", "private_token"}
                for k, _ in parse_qsl(parts.query, keep_blank_values=True)
            )
        ):
            raise ValueError
    except ValueError:
        raise GCError("Refused untrusted release transfer URL.") from None
    return value


def filename_key(name: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", name).casefold())


def asset_map(release: dict) -> dict[str, dict]:
    rows = release.get("assets")
    if not isinstance(rows, list):
        raise GCError("Missing release asset list.")
    result = {}
    folded = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GCError("Invalid release asset.")
        name = safe_name(row.get("name"))
        key = filename_key(name)
        if key in folded:
            raise GCError("Ambiguous release asset names.")
        folded.add(key)
        result[name] = row
    return result


_REF_PATH = r"[^/]+(?:/[^/]+)*"
_ARCHIVE_PATH = re.compile(rf"/[^/]+/[^/]+/-/archive/{_REF_PATH}/[^/]+")
_ATTACHMENT_PATH = re.compile(
    rf"/[^/]+/[^/]+/(?:releases/download/{_REF_PATH}/[^/]+|-/releases/{_REF_PATH}/downloads/[^/]+)"
)
_MEDIA_TYPE = re.compile(r"[a-zA-Z0-9!#$&^_.+-]+/[a-zA-Z0-9!#$&^_.+-]+")


def _asset_route(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.hostname not in _WEB_HOSTS:
        return None
    for segment in parts.path.split("/"):
        decoded = unquote(segment)
        if "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/")):
            return None
    if _ARCHIVE_PATH.fullmatch(parts.path):
        return "archive"
    if _ATTACHMENT_PATH.fullmatch(parts.path):
        return "attachment"
    return None


def is_archive(asset: dict) -> bool:
    # Explicit provider types can also accompany direct, signed storage URLs.
    kind = asset.get("type")
    if kind in ("SOURCE", "ATTACH_FILE"):
        return kind == "SOURCE"
    legacy = {"zip", "tar", "tar.gz", "tar.bz2"}
    if kind is not None and not isinstance(kind, str):
        raise GCError("Unrecognized release asset type.")
    url = asset_url(asset.get("browser_download_url"))
    route = _asset_route(url)
    if route == "archive" and (kind is None or (kind in legacy and urlsplit(url).path.endswith("." + kind))):
        return True
    identity = asset.get("id")
    has_id = type(identity) is int and identity > 0
    # Some documented payloads use a MIME type for an attachment. A MIME type
    # alone (or just a .zip filename) is not enough to distinguish it from source.
    if kind is not None:
        if route == "attachment" and has_id and _MEDIA_TYPE.fullmatch(kind):
            return False
        raise GCError("Unrecognized release asset type or route.")
    if route == "attachment" or (has_id and route != "archive"):
        return False
    raise GCError("Cannot distinguish a release attachment from a generated archive.")


def select_assets(release: dict, patterns: tuple[str, ...], archive: str | None) -> list[dict]:
    matches = []
    for name, asset in asset_map(release).items():
        generated = is_archive(asset)
        if archive:
            if generated and name.endswith("." + archive):
                matches.append(asset)
        elif not generated and (not patterns or any(fnmatchcase(name, p) for p in patterns)):
            matches.append(asset)
    if not matches or (archive and len(matches) != 1):
        raise GCError("No unambiguous matching release assets.")
    return matches


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _open(request: Request):
    return build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=60)


def _download_response(url: str, *, secret: str):
    for _ in range(6):
        reject_reflected_credential(url, secret)
        try:
            return _open(Request(asset_url(url), headers={"Accept-Encoding": "identity"}))
        except HTTPError as exc:
            with exc:
                location = exc.headers.get("location")
                if exc.code not in _REDIRECTS or not location:
                    raise GCError(f"Release download failed (HTTP {exc.code}).") from None
                url = urljoin(url, location)
    raise GCError("Too many release download redirects.")


def _expected_integrity(asset: dict) -> tuple[int | None, str | None]:
    size = asset.get("size")
    digest = asset.get("digest")
    if size is not None and (type(size) is not int or size < 0):
        raise GCError("Invalid release asset size.")
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"(?:sha256:)?[a-fA-F0-9]{64}", digest):
            raise GCError("Invalid release asset SHA-256 digest.")
        digest = digest.split(":")[-1].lower()
    return size, digest


def matches_gitcode_attachment_route(url: Any, *, owner: str, repo: str, tag: str, name: str) -> bool:
    # Use the observed GitCode web route as identity metadata, not a transfer URL.
    # Exact comparison with locally quoted components excludes URL aliases,
    # credentials, query/fragment data and ambiguous path normalization.
    base = f"https://gitcode.com/{owner}/{repo}/releases/download/"
    filename = quote(name, safe="")
    return isinstance(url, str) and url in (
        f"{base}{quote(tag, safe='/')}/{filename}",
        f"{base}{quote(tag, safe='')}/{filename}",
    )


def named_checksum(release: dict, name: str, *, owner: str, repo: str, tag: str) -> tuple[int | None, str]:
    assets = asset_map(release)
    asset = assets.get(name)
    error = "No identified uploaded attachment matches the exact filename."
    if asset is None or type(asset.get("id")) is not int or asset["id"] <= 0:
        raise GCError(error)
    kind = asset.get("type")
    if kind != "ATTACH_FILE" and not (
        kind == "attach"
        and matches_gitcode_attachment_route(
            asset.get("browser_download_url"), owner=owner, repo=repo, tag=tag, name=name
        )
    ):
        raise GCError(error)
    if any(row is not asset and row.get("id") == asset["id"] for row in assets.values()):
        raise GCError("Ambiguous release attachment ID.")
    size, digest = _expected_integrity(asset)
    if digest is None:
        raise GCError("GitCode did not supply a SHA-256 for this attachment.")
    return size, digest


class _Writer(Protocol):
    def write(self, data: bytes, /) -> int: ...


def download(asset: dict, target: _Writer, *, secret: str = "") -> None:
    size, digest = _expected_integrity(asset)
    checksum = hashlib.sha256()
    count = 0
    try:
        with _download_response(asset_url(asset.get("browser_download_url")), secret=secret) as response:
            if response.status != 200:
                raise GCError("Release server did not return a complete file.")
            mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if mime in {"text/html", "application/xhtml+xml"} and not str(asset.get("name", "")).lower().endswith(
                (".html", ".htm", ".xhtml")
            ):
                raise GCError("Release server returned a web page instead of the requested asset.")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise GCError("Unexpected release transfer encoding.")
            length = response.headers.get("Content-Length")
            if length is not None and (not re.fullmatch(r"[0-9]{1,20}", length) or size not in {None, int(length)}):
                raise GCError("Release asset length mismatch.")
            expected = int(length) if length is not None else size
            while block := response.read(128 * 1024):
                count += len(block)
                if expected is not None and count > expected:
                    raise GCError("Release asset is larger than declared.")
                checksum.update(block)
                if target.write(block) != len(block):
                    raise GCError("Incomplete local release asset write.")
        if (expected is not None and count != expected) or (digest is not None and digest != checksum.hexdigest()):
            raise GCError("Release asset integrity check failed.")
    except (HTTPException, OSError, ValueError):
        raise GCError("Release download interrupted; no partial file was installed.") from None


class _UploadBody:
    def __init__(self, stream: BinaryIO):
        self.stream = stream
        self.size = 0
        self.digest = hashlib.sha256()

    def read(self, amount: int = -1) -> bytes:
        block = self.stream.read(amount)
        self.size += len(block)
        self.digest.update(block)
        return block


def check_registration(asset: dict, sent: tuple[int, str]) -> None:
    size, digest = _expected_integrity(asset)
    if is_archive(asset) or (size is not None and size != sent[0]) or (digest is not None and digest != sent[1]):
        raise GCError("Uploaded asset metadata does not match the file sent; inspect the release before retrying.")


def upload(stream: BinaryIO, size: int, ticket: dict) -> tuple[int, str]:
    url = asset_url(ticket.get("url"), upload=True)
    raw = ticket.get("headers")
    if (
        not isinstance(raw, dict)
        or {str(k).lower() for k in raw} != _UPLOAD_HEADERS
        or len(raw) != len(_UPLOAD_HEADERS)
    ):
        raise GCError("Unexpected release upload headers.")
    headers = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value or not all(32 <= ord(c) < 127 for c in value):
            raise GCError("Invalid release upload header.")
        headers[key] = value
    try:
        headers["Content-Length"] = str(size)
        body = _UploadBody(stream)
        request = Request(url, method="PUT", headers=headers, data=body)  # type: ignore[arg-type]
        with _open(request) as response:
            if response.status not in {200, 201, 204} or body.size != size:
                raise GCError("Upload not confirmed; inspect the release before retrying.")
        return body.size, body.digest.hexdigest()
    except HTTPError as exc:
        with exc:
            raise GCError(f"Upload not confirmed (HTTP {exc.code}); inspect the release before retrying.") from None
    except (OSError, ValueError, HTTPException):
        raise GCError("Upload interrupted; inspect the release before retrying.") from None
