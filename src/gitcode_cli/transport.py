"""Credential-agnostic response buffering; entry points retain transport policy."""

from __future__ import annotations

import httpx


class ResponseTooLargeError(Exception):
    """Decoded-body overflow with a fixed message and no response-specific fields."""

    def __init__(self) -> None:
        super().__init__("Response exceeds the configured byte limit.")


def read_response_bytes(response: httpx.Response, *, max_response_bytes: int | None) -> bytes:
    """Read decoded bytes, rejecting overflow rather than returning a partial body.

    ``max_response_bytes`` must be an exact positive built-in int, or explicitly
    None for unlimited buffering. It is validated before consuming the stream.
    The limit counts bytes after HTTP content decoding, not Content-Length; it
    does not bound temporary memory used by HTTPX's decompressor.

    The caller owns the response context and must close it on every outcome.
    This helper neither sends requests nor interprets status, credentials, text,
    JSON, or pagination. HTTPX stream errors propagate unchanged so the entry
    point can apply its own safe error mapping; do not expose their raw text.
    """
    if max_response_bytes is not None and (type(max_response_bytes) is not int or max_response_bytes < 1):
        raise ValueError("max_response_bytes must be a positive built-in int or None.")
    content = bytearray()
    # Rechunking could buffer a known overflow byte and consume another stream
    # chunk (or fail there) before yielding it. Inspect native decoded chunks.
    for chunk in response.iter_bytes():
        if max_response_bytes is not None and len(content) + len(chunk) > max_response_bytes:
            raise ResponseTooLargeError
        content.extend(chunk)
    return bytes(content)
