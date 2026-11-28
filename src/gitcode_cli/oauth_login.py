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
from dataclasses import dataclass

from .config import valid_login
from .errors import AuthError
from .oauth_broker_client import _ENTRY, _NONCE, BrokerReceipt, _origin, acquire_receipt
from .oauth_credential_store import OAuthCredentialStore, _PreparedCredential
from .oauth_identity import OAuthIdentity

_Present = Callable[[str, str], Awaitable[None]]
_Acquire = Callable[[str, _Present], Awaitable[BrokerReceipt]]
_Show = Callable[[str], None]
_IDENTITY_WAIT_SECONDS = 30


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


@dataclass(frozen=True)
class _TerminalSession:
    check_foreground: Callable[[], None]
    write_pair: _Show

    def show(self, pair: str) -> None:
        self.check_foreground()
        self.write_pair(pair)


@contextmanager
def _terminal() -> Iterator[_TerminalSession]:
    # Never degrade to printing on stdout/stderr, even when opening the
    # controlling terminal fails. Require a foreground interactive invocation.
    if not all(_terminal_fd(fd) for fd in (0, 2)):
        raise _failed()
    device = "CONOUT$" if sys.platform == "win32" else "/dev/tty"
    fd = os.open(device, os.O_WRONLY | getattr(os, "O_NOCTTY", 0))
    with os.fdopen(fd, "w", encoding="ascii") as out:

        def check_foreground() -> None:
            # Recheck this exact descriptor, not a saved isatty result or
            # whatever stream happens to be named stderr at presentation time.
            if not _terminal_fd(out.fileno()):
                raise _failed()

        def write_pair(pair: str) -> None:
            out.write(
                f"Enter this one-time pairing value only on the trusted broker page opened for this login:\n{pair}\n"
            )
            out.flush()

        check_foreground()
        yield _TerminalSession(check_foreground, write_pair)


def _open_browser(url: str) -> None:
    # The only supported native vault today is Windows. No $BROWSER command,
    # shell interpolation, clipboard integration, or executable discovery.
    if sys.platform != "win32":
        raise _failed()
    os.startfile(url, "open")


class _Presentation:
    def __init__(self, url: str, terminal: _TerminalSession, opener: Callable[[str], None]) -> None:
        self.url = url
        self.terminal = terminal
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
        self.terminal.check_foreground()
        self.opener(self.url)
        self.terminal.show(pair)
        self.completed = True


async def _prepare_credential(
    store: OAuthCredentialStore, receipt: BrokerReceipt, expected_login: str | None = None
) -> _PreparedCredential:
    # Reject a different broker claim before /user. Bind preparation itself to
    # the caller's account: the store verifies this exact login AND subject
    # against /user before returning one-use material for the native vault.
    account_login = receipt.login
    if expected_login is not None:
        if type(account_login) is not str or account_login != expected_login:
            raise _failed()
        account_login = expected_login

    # The worker is read-only. Python may still wait for a running verifier
    # during executor teardown, but that worker can never access the vault.
    task = asyncio.create_task(
        asyncio.to_thread(
            store._prepare,
            subject=receipt.subject,
            login=account_login,
            expires_at=receipt.expires_at,
            access_token=receipt.access_token,
        )
    )
    try:
        # asyncio.wait() preserves external cancellation even when verification
        # completes at the same time (older asyncio.wait_for() may swallow it).
        done, _ = await asyncio.wait((task,), timeout=_IDENTITY_WAIT_SECONDS)
        if not done:
            raise _failed()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
        elif not task.cancelled():
            # Observe any simultaneous worker failure so asyncio cannot log it.
            task.exception()


async def login_with_browser(
    trusted_broker_origin: str,
    *,
    expected_login: str | None = None,
    _open_terminal: Callable[[], AbstractContextManager[_TerminalSession]] = _terminal,
    _opener: Callable[[str], None] = _open_browser,
    _acquire: _Acquire = acquire_receipt,
    _store_factory: Callable[[], OAuthCredentialStore] = OAuthCredentialStore.system,
) -> OAuthIdentity:
    """Log in once; if supplied, require the exact expected login before any vault write."""
    try:
        if expected_login is not None and (type(expected_login) is not str or not valid_login(expected_login)):
            raise _failed()
        origin = _origin(trusted_broker_origin)
        with _open_terminal() as terminal:
            store = _store_factory()
            if type(store) is not OAuthCredentialStore:
                raise _failed()
            presentation = _Presentation(origin + _ENTRY, terminal, _opener)
            try:
                receipt = await _acquire(origin, presentation.present)
            finally:
                presentation.available = False
            if not presentation.completed or type(receipt) is not BrokerReceipt:
                raise _failed()
        # A cancellation already requested at receipt should not start /user.
        await asyncio.sleep(0)
        prepared = await _prepare_credential(store, receipt, expected_login)
        # Deliver pending cancellation after identity verification and before
        # native commit. Once the synchronous put/readback begins, do not retry,
        # invent success, or delete a possibly valid concurrent replacement.
        await asyncio.sleep(0)
        who = store._commit(prepared)
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
