"""Request-scoped transport redaction without retaining credentials in log filters."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote, quote_plus

_secret: ContextVar[str] = ContextVar("gitcode_request_secret", default="")
_QUERY_SECRET = re.compile(r"(?i)(access_token=)[^&\s\"'<>]+")


def redact(value: object, token: str = "") -> str:
    text = str(value)
    if token:
        for variant in {token, quote(token, safe=""), quote_plus(token)}:
            text = text.replace(variant, "[REDACTED]")
    return _QUERY_SECRET.sub(r"\1[REDACTED]", text)


class _TransportFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format before handlers see the record, including handlers installed by
        # embedding applications. Never suppress unrelated transport diagnostics.
        record.msg = redact(record.getMessage(), _secret.get())
        record.args = ()
        return True


_FILTER = _TransportFilter()


@contextmanager
def redacted_transport(token: str):
    for name in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy"):
        logging.getLogger(name).addFilter(_FILTER)
    context = _secret.set(token)
    try:
        yield
    finally:
        _secret.reset(context)
