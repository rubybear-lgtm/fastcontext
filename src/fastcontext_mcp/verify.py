"""Separate registration, import, MCP connection, and inference diagnostics."""

import argparse
import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path

from fastcontext_mcp.configwriter import TOOL_CONFIGS


def read_registration(tool, *, home=None):
    """Validate the real entry and its launch path without changing configuration."""
    cfg = TOOL_CONFIGS[tool]
    path = (home or Path.home()) / cfg["path"]
    content = path.read_text()
    config = tomllib.loads(content) if cfg["format"] == "toml" else json.loads(content)
    entry = config.get(cfg["container_key"], {}).get(cfg["entry_name"])
    if not isinstance(entry, dict):
        raise ValueError(f"No FastContext MCP entry in {path}")
    if entry.get("enabled") is False:
        raise ValueError(f"FastContext is disabled in {path}")
    command = entry.get("command")
    if tool == "opencode":
        if entry.get("type") != "local":
            raise ValueError("Expected a local OpenCode MCP entry")
        if not isinstance(command, list) or not command:
            raise ValueError("Expected a nonempty command array")
        command, args = command[0], command[1:]
    else:
        args = entry.get("args", [])
    if not isinstance(command, str) or not Path(command).is_absolute():
        raise ValueError("MCP command must be an absolute executable path (expand ~ before saving)")
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        raise ValueError("MCP arguments must be a list of strings")
    if not Path(command).is_file() or not os.access(command, os.X_OK):
        raise ValueError(f"MCP executable is missing or not executable: {command}")
    return command, args, entry


async def check_connection(command, args, entry, *, work_dir=None, inference=False):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=command,
        args=args,
        env={**os.environ, **entry.get("env", {})},
        cwd=entry.get("cwd"),
    )
    async with asyncio.timeout(610 if inference else 30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if "fastcontext_explore" not in {tool.name for tool in tools.tools}:
                    raise ValueError("Connected MCP server does not expose fastcontext_explore")
                print("Connection: MCP handshake and tool discovery passed")
                if inference:
                    result = await session.call_tool(
                        "fastcontext_explore",
                        {"query": "Find the project manifest and report its project name with a source citation.",
                         "max_turns": 1, "work_dir": str(work_dir)},
                    )
                    if result.isError or not result.content:
                        raise ValueError(f"Inference request failed: {result}")
                    print("Inference: request completed; inspect citations before trusting the answer")
                    for block in result.content:
                        if block.type == "text":
                            print(block.text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=TOOL_CONFIGS, required=True)
    parser.add_argument("--connect", action="store_true", help="Test the configured MCP launch command")
    parser.add_argument("--inference", action="store_true", help="Also load the model and run one exploration")
    parser.add_argument("--work-dir", type=Path, help="Absolute repository directory for inference")
    args = parser.parse_args(argv)
    if args.inference and (
        args.work_dir is None or not args.work_dir.is_absolute() or not args.work_dir.is_dir()
    ):
        parser.error("--inference requires --work-dir pointing to an existing absolute directory")
    try:
        command, launch_args, entry = read_registration(args.tool)
        print("Registration: parsed entry and executable path passed")
        from fastcontext_mcp.server import mcp  # noqa: F401

        print("Import: lightweight MCP server imports; model loading has not been tested")
        if args.connect or args.inference:
            asyncio.run(check_connection(
                command, launch_args, entry, work_dir=args.work_dir, inference=args.inference,
            ))
    except Exception as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
