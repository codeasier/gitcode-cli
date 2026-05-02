from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AdapterActionResult:
    item: dict[str, Any] | None = None
    items: list[dict[str, Any]] | None = None
    message: str | None = None
    warning: str | None = None
    degraded: bool = False
    approximated: bool = False
