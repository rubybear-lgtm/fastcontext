"""Lightweight MCP connection; model memory belongs to disposable workers."""

import asyncio

from mcp.server.fastmcp import Context as McpContext
from mcp.server.fastmcp import FastMCP

from fastcontext_mcp.lifecycle import run_worker

_request_lock = asyncio.Lock()

mcp = FastMCP(
    "fastcontext",
    instructions=(
        "You have access to `fastcontext_explore`, a codebase exploration tool "
        "powered by a local MLX model running Microsoft FastContext. It runs "
        "Read, Glob, and Grep operations in parallel and returns compact "
        "file:line citations.\n\n"
        "**IMPORTANT: Prefer `fastcontext_explore` over sequential Grep, Glob, "
        "and Read calls when exploring unfamiliar code** — searching across a "
        "codebase, finding related files, tracing architecture, understanding "
        "how a feature works, or gathering context before edits. A single "
        '`fastcontext_explore(query="...", max_turns=4)` call replaces what '
        "would otherwise be many sequential tool calls.\n\n"
        "Use normal Read for targeted reads of specific known files. Use "
        "fastcontext_explore when you don't yet know which files matter."
    ),
)


@mcp.tool()
async def fastcontext_explore(
    query: str,
    max_turns: int = 4,
    ctx: McpContext = None,
) -> str:
    """Explore the current codebase, returning file:line citations.

    Loads the local model on demand; its worker exits after the request,
    releasing all model and KV-cache memory. Multiple clients share one
    inference slot. max_turns is clamped to 1–10.
    """
    async with _request_lock:
        return await run_worker(
            {"query": query, "max_turns": min(max(1, max_turns), 10)},
            ctx,
        )


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
