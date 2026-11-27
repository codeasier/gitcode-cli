"""One internal, interactive CLI-broker login. No command, PAT fallback or refresh.

The origin must be pinned independently by the application, never discovered from
the repository, process environment or broker response. Dependencies prefixed
with an underscore are trusted, in-process seams for offline integration tests.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from .errors import AuthError
from .oauth_broker_client import _ENTRY, _NONCE, BrokerReceipt, _origin, acquire_receipt
from .oauth_credential_store import OAuthCredentialStore
from .oauth_identity import OAuthIdentity

_Present = Callable[[str, str], Awaitable[None]]
_Acquire = Callable[[str, _Present], Awaitable[BrokerReceipt]]
_Show = Callable[[str], None]


def _failed() -> AuthError:
    return AuthError("OAuth login was not confirmed; do not retry this transaction.")


def _terminal_fd(fd: int) -> bool:
    if not os.isatty(fd):
        return False
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415 - Windows-only API

        # The CRT isatty check alone also accepts character devices such as NUL.
        kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True, winmode=0x00000800)
        mode = ctypes.c_uint32()
        get_mode = kernel.GetConsoleMode
        get_mode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        get_mode.restype = ctypes.c_int32
        return bool(get_mode(msvcrt.get_osfhandle(fd), ctypes.byref(mode)))
    return os.tcgetpgrp(fd) == os.getpgrp()


@contextmanager
def _terminal() -> Iterator[_Show]:
    # Never degrade to printing on stdout/stderr, even when opening the
    # controlling terminal fails. Require a foreground interactive invocation.
    if not all(_terminal_fd(fd) for fd in (0, 2)):
        raise _failed()
    device = "CONOUT$" if sys.platform == "win32" else "/dev/tty"
    fd = os.open(device, os.O_WRONLY | getattr(os, "O_NOCTTY", 0))
    with os.fdopen(fd, "w", encoding="ascii") as out:
        if not _terminal_fd(out.fileno()):
            raise _failed()

        def show(pair: str) -> None:
            out.write(
                f"Enter this one-time pairing value only on the trusted broker page opened for this login:\n{pair}\n"
            )
            out.flush()

        yield show


def _open_browser(url: str) -> None:
    # The only supported native vault today is Windows. No $BROWSER command,
    # shell interpolation, clipboard integration, or executable discovery.
    if sys.platform != "win32":
        raise _failed()
    os.startfile(url, "open")


class _Presentation:
    def __init__(self, url: str, show: _Show, opener: Callable[[str], None]) -> None:
        self.url = url
        self.show = show
        self.opener = opener
        self.available = True
        self.completed = False

    async def present(self, url: str, pair: str) -> None:
        allowed, self.available = self.available, False
        self.completed = False
        if not allowed or type(url) is not str or url != self.url or type(pair) is not str or len(pair) != 87:
            raise _failed()
        selector, dot, secret = pair.partition(".")
        if not dot or selector == secret or not _NONCE.fullmatch(selector) or not _NONCE.fullmatch(secret):
            raise _failed()
        self.opener(self.url)
        self.show(pair)
        self.completed = True


async def login_with_browser(
    trusted_broker_origin: str,
    *,
    _open_terminal: Callable[[], AbstractContextManager[_Show]] = _terminal,
    _opener: Callable[[str], None] = _open_browser,
    _acquire: _Acquire = acquire_receipt,
    _store_factory: Callable[[], OAuthCredentialStore] = OAuthCredentialStore.system,
) -> OAuthIdentity:
    """Acquire exactly once; return only the verified and read-back account identity."""
    try:
        origin = _origin(trusted_broker_origin)
        with _open_terminal() as show:
            store = _store_factory()
            if type(store) is not OAuthCredentialStore:
                raise _failed()
            presentation = _Presentation(origin + _ENTRY, show, _opener)
            try:
                receipt = await _acquire(origin, presentation.present)
            finally:
                presentation.available = False
            if not presentation.completed or type(receipt) is not BrokerReceipt:
                raise _failed()
        # Honor a pending cancellation before any irreversible vault write.
        await asyncio.sleep(0)
        # save() revalidates fields, verifies the owner via fixed-origin GitCode
        # /user, writes the native vault once, and reads the exact credential back.
        # Never retry or delete on an uncertain outcome (possibly a concurrent write).
        who = store.save(
            subject=receipt.subject,
            login=receipt.login,
            expires_at=receipt.expires_at,
            access_token=receipt.access_token,
        )
        if type(who) is not OAuthIdentity or who != OAuthIdentity(receipt.subject, receipt.login):
            raise _failed()
        return who
    except asyncio.CancelledError:
        error = asyncio.CancelledError()
    except Exception:
        error = _failed()
    # Preserve cancellation without retaining native/transport messages or
    # exception chains. `from None` alone would leave __context__ attached.
    raise error
