"""Command-line entry point for the Orca GitCode linker."""

from __future__ import annotations

import argparse

from . import __version__
from .linker import (
    DEFAULT_CACHE_TTL,
    DEFAULT_TIMEOUT,
    GITCODE_API_BASE,
    LinkerConfig,
    LinkerServer,
    _log,
    make_gitcode_fetch,
    resolve_token,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve GitCode pull requests as a local Gitea-compatible API for Orca."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
    parser.add_argument("--token", help="GitCode access token (default: GC_TOKEN or gc config).")
    parser.add_argument("--token-file", help="File containing a GitCode access token.")
    parser.add_argument(
        "--api-base",
        default=GITCODE_API_BASE,
        help=f"GitCode API base (default: {GITCODE_API_BASE}).",
    )
    parser.add_argument(
        "--cache-ttl",
        type=float,
        default=DEFAULT_CACHE_TTL,
        help="Cache seconds (default: 15).",
    )
    parser.add_argument(
        "--fork-pr-source",
        choices=("both", "parent", "origin"),
        default="both",
        help="For a GitCode fork, read PRs from both (default), the upstream parent, or only origin.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Upstream timeout seconds (default: 15).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        _log("invalid port")
        return 2
    token, token_source = resolve_token(args.token, args.token_file)
    if not token:
        _log("no GitCode token found; run gc auth login or set GC_TOKEN")
    config = LinkerConfig(
        token=token,
        api_base=args.api_base,
        cache_ttl=max(args.cache_ttl, 0.0),
        fork_pr_source=args.fork_pr_source,
        fetch=make_gitcode_fetch(args.api_base, token, max(args.timeout, 1.0)),
    )
    try:
        server = LinkerServer((args.host, args.port), config)
    except OSError as error:
        _log(f"cannot bind {args.host}:{args.port}: {error}")
        return 1
    _log(f"listening on http://{args.host}:{args.port}/api/v1 (token: {token_source})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
