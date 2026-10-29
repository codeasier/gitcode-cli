"""Short-lived Git credential prompt handler; never invoke through MCP."""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit


def answer(prompt: str, token: str, username: str) -> str | None:
    """Only supply credentials for an HTTPS GitCode prompt, never a redirected host."""
    if "'" not in prompt:
        return None
    try:
        url = urlsplit(prompt.split("'", 2)[1])
        if url.scheme != "https" or url.hostname != "gitcode.com" or url.port not in (None, 443):
            return None
    except ValueError:
        return None
    if prompt.startswith("Username for "):
        return username
    if prompt.startswith("Password for "):
        return token
    return None


def main() -> int:
    value = answer(
        sys.argv[1] if len(sys.argv) == 2 else "",
        os.environ.get("GITCODE_CLONE_TOKEN", ""),
        os.environ.get("GITCODE_CLONE_USERNAME", ""),
    )
    if not value:
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
