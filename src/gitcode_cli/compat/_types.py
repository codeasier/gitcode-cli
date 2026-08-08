"""Shared types and constants for the compat registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CompatStatus(str, Enum):
    """Classification of a ``gc`` command/flag against the ``gh`` baseline."""

    IMPLEMENTED = "implemented"
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    NOT_IN_CLI = "not_in_cli"


@dataclass(frozen=True)
class CompatEntry:
    """One row of the compatibility matrix.

    ``command`` is a space-separated path without the leading ``gc`` (e.g.
    ``"issue list"``). ``flag`` is the long-form flag (``"--app"``) or ``None``
    when the entry describes a whole subcommand.

    ``pending_key`` must match the literal string passed to
    ``_pending_gh_compat()`` for ``PENDING`` entries. ``unsupported_key`` must
    match the capability key passed to ``unsupported()`` for ``UNSUPPORTED``
    entries (and the key must exist in ``CAPABILITY_MESSAGES``).
    """

    command: str
    flag: str | None
    status: CompatStatus
    note: str = ""
    pending_key: str | None = None
    unsupported_key: str | None = None
    gc_extension: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def label(self) -> str:
        """Human-readable label used in the rendered report."""
        if self.flag is None:
            return self.command
        aliases = "/".join((self.aliases or ()) + ((self.flag,) if self.flag else ()))
        if not aliases:
            return f"{self.command} (no flag)"
        return f"{self.command} {aliases}"
