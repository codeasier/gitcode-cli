"""Fail-closed local file boundaries for release transfers on POSIX."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryFile
from typing import BinaryIO

from .errors import GCError
from .release_assets import download, filename_key, safe_name


def _supported() -> None:
    if os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        raise GCError("Secure release file access is unavailable on this platform. Downloads may use --output -.")


def _trusted(result: os.stat_result, *, allow_sticky: bool) -> bool:
    # Root and the invoking user are trusted. A writable sticky ancestor such as
    # /tmp can only lead to a separately checked child; never write files there.
    return result.st_uid in (0, os.geteuid()) and (
        not result.st_mode & 0o022 or (allow_sticky and bool(result.st_mode & stat.S_ISVTX))
    )


def _dir_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY


def _identity(result: os.stat_result) -> tuple[int, int]:
    return result.st_dev, result.st_ino


def _revision(result: os.stat_result) -> tuple[int, int, int]:
    return result.st_size, result.st_mtime_ns, result.st_ctime_ns


@contextmanager
def directory(path: Path, *, create: bool = False, writable: bool = False) -> Iterator[int]:
    """Walk from a trusted absolute root without following any symlink."""
    _supported()
    absolute = path.absolute()
    if ".." in absolute.parts or absolute.anchor != "/":
        raise GCError("Use a release path without '..' components or a noncanonical root.")
    fd = os.open("/", _dir_flags())
    try:
        for name in absolute.parts[1:]:
            if not _trusted(os.fstat(fd), allow_sticky=True):
                raise GCError("Use a release path under trusted directories.")
            try:
                child = os.open(name, _dir_flags(), dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                if not _trusted(os.fstat(fd), allow_sticky=False):
                    raise GCError("Refusing to create a release directory under a shared directory.") from None
                os.mkdir(name, mode=0o700, dir_fd=fd)
                child = os.open(name, _dir_flags(), dir_fd=fd)
            os.close(fd)
            fd = child
        if not _trusted(os.fstat(fd), allow_sticky=not writable):
            raise GCError("Use a release path under trusted directories.")
        yield fd
    finally:
        os.close(fd)


@dataclass(frozen=True)
class UploadInput:
    name: str
    stream: BinaryIO
    size: int


MAX_CHECK_BYTES = 1024 * 1024 * 1024


def check_local_digest(path: Path, size: int | None, expected: str) -> None:
    """Compare a stable local file to a mandatory SHA-256, without staging or modifying it."""
    try:
        with directory(path.parent) as parent, ExitStack() as cleanup:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            cleanup.callback(os.close, fd)  # fdopen itself can fail (e.g. a directory).
            with os.fdopen(fd, "rb", closefd=False) as source:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or not _trusted(before, allow_sticky=False):
                    raise GCError("Use a trusted regular file, not a link or a shared-writable file.")
                if before.st_size > MAX_CHECK_BYTES:
                    raise GCError("Local file exceeds the 1 GiB checksum limit.")
                if size is not None and before.st_size != size:
                    raise GCError("Local file size differs from the release attachment.")
                digest = hashlib.sha256()
                count = 0
                while block := source.read(min(128 * 1024, before.st_size - count + 1)):
                    count += len(block)
                    if count > before.st_size:
                        raise GCError("Local file changed while computing its checksum.")
                    digest.update(block)
                with directory(path.parent) as current:
                    visible = os.stat(path.name, dir_fd=current, follow_symlinks=False)
                    if (
                        _identity(os.fstat(current)) != _identity(os.fstat(parent))
                        or _identity(visible) != _identity(before)
                        or _revision(visible) != _revision(before)
                        or _revision(os.fstat(fd)) != _revision(before)
                        or count != before.st_size
                    ):
                        raise GCError("Local file changed while computing its checksum.")
                if digest.hexdigest() != expected:
                    raise GCError("SHA-256 differs from the release attachment metadata.")
    except OSError:
        raise GCError("Cannot read a trusted regular file without following links.") from None


def _snapshot(path: Path, stream: BinaryIO) -> int:
    with directory(path.parent) as parent:
        source = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(source)
            if not stat.S_ISREG(before.st_mode) or not _trusted(before, allow_sticky=False):
                raise GCError("Upload inputs must be trusted regular files, not links or shared-writable files.")
            with os.fdopen(source, "rb", closefd=False) as input_file:
                shutil.copyfileobj(input_file, stream, 128 * 1024)
            size = stream.tell()
            if size != before.st_size or _revision(before) != _revision(os.fstat(source)):
                raise GCError("Upload source changed while preparing the file; no remote write was attempted.")
            stream.seek(0)
            return size
        finally:
            os.close(source)


@contextmanager
def uploads(paths: tuple[Path, ...]) -> Iterator[list[UploadInput]]:
    """Stage every input before the caller can publish or delete anything."""
    with ExitStack() as resources:
        staged = []
        names = set()
        try:
            for path in paths:
                name = safe_name(path.name)
                key = filename_key(name)
                if key in names:
                    raise GCError("Upload filenames collide after Unicode and case normalization.")
                names.add(key)
                stream = resources.enter_context(TemporaryFile())
                staged.append(UploadInput(name, stream, _snapshot(path, stream)))
        except OSError:
            raise GCError("Cannot safely stage upload input; use a regular file with no symlink components.") from None
        yield staged


def exists(parent: int, name: str) -> bool:
    try:
        result = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(result.st_mode):
        raise GCError("Refusing non-regular release destination.")
    return True


@contextmanager
def _private_stage(parent: int) -> Iterator[int]:
    name = ".gc-release-" + token_hex(16)
    os.mkdir(name, mode=0o700, dir_fd=parent)
    try:
        stage = os.open(name, _dir_flags(), dir_fd=parent)
        try:
            result = os.fstat(stage)
            if result.st_uid != os.geteuid() or result.st_mode & 0o077:
                raise GCError("Release staging directory is not private.")
            yield stage
        finally:
            os.close(stage)
    finally:
        os.rmdir(name, dir_fd=parent)


def save_verified(
    path: Path, parent: int, name: str, write: Callable[[BinaryIO], None], *, clobber: bool = False
) -> None:
    """Stage privately; publish only after the writer succeeds and the stage closes."""
    with _private_stage(parent) as stage:
        temp = os.open("payload", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=stage)
        try:
            with os.fdopen(temp, "wb", closefd=False) as out:
                write(out)
            verified = os.fstat(temp)
            # If the visible path was removed or relinked, fail rather than
            # report a download at a different location. Writes are still based
            # on the original descriptor, not this check.
            with directory(path, writable=True) as current:
                if _identity(os.fstat(parent)) != _identity(os.fstat(current)):
                    raise GCError("Release destination directory changed during download.")
            staged = os.stat("payload", dir_fd=stage, follow_symlinks=False)
            if _identity(staged) != _identity(verified) or _revision(staged) != _revision(verified):
                raise GCError("Release staging file changed during download.")
            if clobber:
                exists(parent, name)
                os.replace("payload", name, src_dir_fd=stage, dst_dir_fd=parent)
            else:
                # link() is atomic create-if-absent; no race on an exists() check.
                os.link("payload", name, src_dir_fd=stage, dst_dir_fd=parent, follow_symlinks=False)
        finally:
            os.close(temp)
            with suppress(FileNotFoundError):
                os.unlink("payload", dir_fd=stage)


def save(asset: dict, path: Path, parent: int, name: str, *, clobber: bool, secret: str) -> None:
    def write(out: BinaryIO) -> None:
        download(asset, out, secret=secret)

    save_verified(path, parent, name, write, clobber=clobber)
