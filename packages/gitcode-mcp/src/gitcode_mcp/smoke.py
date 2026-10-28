"""Exercise the installed package over a real stdio MCP connection."""

from __future__ import annotations

import argparse
import os
import sys

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from .config import repository_name


async def check(repository: str | None = None) -> int:
    environment = dict(os.environ)
    environment["GITCODE_MCP_READ_ONLY"] = "true"
    if not repository:
        # Offline means no API calls, not "try a real account if it happens to be configured".
        environment.pop("GITCODE_TOKEN", None)
        environment.pop("GC_TOKEN", None)
    parameters = StdioServerParameters(
        command=sys.executable, args=["-I", "-m", "gitcode_mcp"], env=environment
    )
    with anyio.fail_after(30):
        async with Client(parameters) as client:
            tools = (await client.list_tools()).tools
            names = {tool.name for tool in tools}
            assert "gitcode_get_repository" in names, "Repository read tool missing"
            assert tools and all(
                tool.annotations and tool.annotations.read_only_hint for tool in tools
            )
            invalid = await client.call_tool(
                "gitcode_get_repository", {"owner": "../escape", "repo": "test"}
            )
            assert invalid.is_error, "Invalid repository input was accepted"
            if repository:
                owner, repo = repository_name(repository).split("/")
                response = await client.call_tool(
                    "gitcode_get_repository", {"owner": owner, "repo": repo}
                )
                if response.is_error:
                    print(
                        "Live repository read failed; check credentials and repository access.",
                        file=sys.stderr,
                    )
                    return 1
    print(
        f"MCP smoke passed: stdio connection, {len(tools)} read tools, input validation"
        + (", live repository read" if repository else "; no network calls")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="optional live read-only check of owner/repo")
    args = parser.parse_args()
    return anyio.run(check, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
