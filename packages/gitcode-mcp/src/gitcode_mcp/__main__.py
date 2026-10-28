"""Console entry point. Stdout is reserved exclusively for the stdio protocol."""

from __future__ import annotations

import argparse
import logging
import sys

import anyio
import uvicorn
from mcp.server.stdio import stdio_server

from . import __version__
from .api import GitCodeAPI
from .config import ConfigurationError, Settings
from .server import create_http_app, create_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GitCode MCP server (credentials from environment)"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port")
    parser.add_argument("--read-only", action="store_true", help="Hide and reject mutation tools")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    try:
        settings = Settings.from_env()
        if args.read_only:
            from dataclasses import replace

            settings = replace(settings, read_only=True)
        if settings.oauth is not None and args.transport != "streamable-http":
            raise ConfigurationError("OAuth mode requires --transport streamable-http.")
        oauth_provider = None
        if settings.oauth is not None:
            from .oauth import GitCodeOAuthProvider
            from .oauth_store import OAuthStoreError

            try:
                oauth_provider = GitCodeOAuthProvider(settings)
            except OAuthStoreError:
                raise ConfigurationError(
                    "Cannot open OAuth storage. Check the database path, permissions and persistent encryption key."
                ) from None
        api = GitCodeAPI(
            settings.token, timeout=settings.timeout, max_response_bytes=settings.max_response_bytes
        )
        try:
            server = create_server(settings, api=api, oauth_provider=oauth_provider)
            if args.transport == "stdio":

                async def serve() -> None:
                    async with stdio_server() as (reader, writer):
                        await server.run(reader, writer, server.create_initialization_options())

                anyio.run(serve)
            else:
                app = create_http_app(server, settings, args.host, oauth_provider=oauth_provider)
                uvicorn.run(
                    app, host=args.host, port=args.port, log_level="warning", access_log=False
                )
        finally:
            api.close()
            if oauth_provider is not None:
                anyio.run(oauth_provider.aclose)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
