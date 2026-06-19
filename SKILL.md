---
name: fastcontext
description: This skill should be used when the user asks to "explore the codebase", "find related files", "understand the architecture", "search for implementations", "use FastContext", or when broad codebase context is needed before editing unfamiliar code. Runs Microsoft FastContext with in-process MLX inference on Apple Silicon.
---

# FastContext

FastContext is a specialized exploration agent that runs Read, Glob, and Grep operations in parallel using a local 4B model via MLX, returning compact file-path:line-range citations.

The model runs in-process via `mlx_lm` — no external server, no env vars, no subprocess management.

## Setup

Install the MCP server package:

```bash
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

If the venv doesn't exist yet:

```bash
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

## Usage

The MCP server exposes `fastcontext_explore` as a tool. When configured as an MCP server in Claude Code, call it directly. The model loads on startup and stays in memory.

For CLI testing:

```bash
~/.cache/fastcontext/venv/bin/fastcontext-mcp
```
