"""Isolated, bounded ZIP transfer for GitCode Actions. Never extract artifact content."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import ssl
import stat
import time
import zipfile
from contextlib import contextmanager, suppress
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import BinaryIO
from urllib.error import HTTPError
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from .errors import APIError

MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_REDIRECTS = 4
MAX_TRANSFER_SECONDS = 300

# The GitCode Actions ZIP endpoint was observed returning this exact CDN host
# (PR #208 provider acceptance). Do not trust domain suffixes or generic storage.
_APPROVED_HOSTS = {
    "api.gitcode.com",
    "gitcode.com",
    "api.atomgit.com",
    "atomgit.com",
    "actions-artifacts-cdn.atomgit.com",
}
_REDIRECTS = {301, 302, 303, 307, 308}
_AUTH_KEYS = {"access_token", "authorization", "private-token", "private_token"}


def _location(base: str, value: str, token: str) -> str:
    try:
        if not value or len(value) > 8192 or not all(33 <= ord(c) <= 126 and c != "\\" for c in value):
            raise ValueError
        url = urljoin(base, value)
        parts = urlsplit(url)
        host = parts.hostname or ""
        if (
            parts.scheme != "https"
            or host not in _APPROVED_HOSTS
            or parts.netloc.lower() not in {host, f"{host}:443"}
            or parts.fragment
            or any(k.lower() in _AUTH_KEYS for k, _ in parse_qsl(parts.query, keep_blank_values=True))
        ):
            raise ValueError
        decoded = url
        for _ in range(3):
            if token and token in decoded:
                raise ValueError
            decoded = unquote(decoded)
    except ValueError:
        raise APIError("Refused an untrusted Actions artifact download location.") from None
    return url


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _connect_public(address, timeout=30, source_address=None):
    # Resolve once and use the vetted addresses directly. The parent HTTPS
    # connection still verifies TLS and sends SNI for the original hostname.
    targets = socket.getaddrinfo(*address, type=socket.SOCK_STREAM)
    if not targets or len(targets) > 8:
        raise OSError("No bounded artifact storage address set.")
    for _family, _kind, _proto, _canonname, target in targets:
        ip = ipaddress.ip_address(target[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise OSError("Artifact storage resolved to a non-public address.")
    end = time.monotonic() + timeout
    for family, kind, proto, _, target in targets:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(remaining)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(target)
        except OSError:
            sock.close()
        else:
            sock.settimeout(timeout)
            return sock
    raise OSError("Cannot connect to artifact storage.")


class _PublicHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSHandler(HTTPSHandler):
    def __init__(self):
        super().__init__()
        self._tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._tls_context.load_default_certs()

    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req, context=self._tls_context)


def _open(url: str):
    # No Authorization, cookies, proxy or on-by-default request URL logging.
    request = Request(url, headers={"Accept": "application/zip", "Accept-Encoding": "identity"})
    return build_opener(ProxyHandler({}), _NoRedirect(), _PublicHTTPSHandler()).open(request, timeout=30)


def _verified_body(response, out: BinaryIO, size: int, sha256: str, end: float) -> None:
    if response.status != 200 or response.headers.get("content-encoding", "identity").lower() != "identity":
        raise APIError("Artifact server did not return an unencoded complete archive.")
    lengths = response.headers.get_all("content-length") or []
    if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,12}", lengths[0]) or int(lengths[0]) != size):
        raise APIError("Artifact Content-Length does not match metadata.")
    count = 0
    actual = hashlib.sha256()
    while True:
        if time.monotonic() >= end:
            raise APIError("Artifact transfer exceeded its time limit.")
        block = response.read1(128 * 1024)
        if not block:
            break
        count += len(block)
        if count > size or count > MAX_ZIP_BYTES:
            raise APIError("Artifact body exceeded its verified size.")
        actual.update(block)
        out.write(block)
    if count != size or actual.hexdigest() != sha256:
        raise APIError("Artifact size or SHA-256 did not match metadata.")
    out.seek(0)
    if out.read(4) not in {b"PK\x03\x04", b"PK\x05\x06"} or not zipfile.is_zipfile(out):
        raise APIError("The downloaded artifact is not a ZIP archive.")


def stream_zip(base: str, location: str, out: BinaryIO, size: int, sha256: str, *, token: str) -> None:
    end = time.monotonic() + MAX_TRANSFER_SECONDS
    try:
        for _ in range(MAX_REDIRECTS + 1):
            url = _location(base, location, token)
            if time.monotonic() >= end:
                break
            try:
                response = _open(url)
            except HTTPError as exc:
                with exc:
                    locations = exc.headers.get_all("location") or []
                    if exc.code not in _REDIRECTS or len(locations) != 1:
                        raise APIError(f"Artifact download failed (HTTP {exc.code}).") from None
                    base, location = url, locations[0]
                    continue
            with response:
                _verified_body(response, out, size, sha256, end)
            return
        raise APIError("Artifact transfer exceeded its redirect or time limit.")
    except (HTTPException, OSError, ValueError):
        raise APIError("Artifact transfer interrupted; no archive was installed.") from None


@contextmanager
def _output_directory(destination: Path):
    absolute = destination.absolute()
    parent = absolute.parent
    # POSIX descriptor-relative filesystem actions prevent path/junction
    # substitutions between validation, streaming and the final link.
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise APIError("Artifact download requires POSIX directory-descriptor support; use 'run artifacts' here.")
    if absolute.suffix.lower() != ".zip" or not absolute.name or ".." in absolute.parts:
        raise APIError("Specify a new .zip output file in an existing directory without '..' components.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(parent.anchor, flags)
    try:
        for part in parent.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _check_directory(directory: int) -> None:
    info = os.fstat(directory)
    if info.st_uid != os.geteuid() or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise APIError("Choose an output directory you own that is not writable by groups or other users.")


def _require_new_output(directory: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise APIError("Artifact output already exists; choose a new path.")


@contextmanager
def preflight_output(destination: Path):
    """Check the destination without creating anything; keep its directory anchored."""
    try:
        absolute = destination.absolute()
        with _output_directory(absolute) as directory:
            _check_directory(directory)
            _require_new_output(directory, absolute.name)
            yield absolute, directory
    except OSError:
        raise APIError("Cannot install the artifact; choose a fresh .zip path in a safe local directory.") from None


def _check_output_path(absolute: Path, directory: int, *, linked: bool = False) -> None:
    # Reopen only for comparison. All mutations remain anchored to the original
    # descriptor, even if the path is replaced immediately after this check.
    try:
        with _output_directory(absolute) as current:
            expected, observed = os.fstat(directory), os.fstat(current)
            if (expected.st_dev, expected.st_ino) == (observed.st_dev, observed.st_ino):
                return
    except OSError:
        pass
    result = "The verified archive may remain in the original directory." if linked else "No archive was installed."
    raise APIError("Artifact output directory changed. " + result)


@contextmanager
def verified_output(absolute: Path, directory: int):
    """Start a private stage after initial provenance checks; publish only on success."""
    name = absolute.name
    # Permissions, pathname and the target may have changed during metadata reads.
    _check_output_path(absolute, directory)
    _check_directory(directory)
    _require_new_output(directory, name)
    temporary = ".gc-artifact-" + uuid4().hex
    fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "w+b") as stage:
            yield stage
            stage.flush()
            os.fsync(stage.fileno())
        _check_directory(directory)
        _check_output_path(absolute, directory)
        # Atomic create-if-absent. Only the original directory can receive the
        # file, even if a link or file appears or its parent is renamed.
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        # Don't report a success path if it was replaced while linking. Never
        # try to unlink the destination: someone could have replaced that entry.
        _check_output_path(absolute, directory, linked=True)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
